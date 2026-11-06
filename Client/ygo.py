# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Yu-Gi-Oh! bots instead of UCI engines (github.com/tsoj/yugioh_AI):
#
#   - An engine is a source tree: the commit's zipball plus its submodules (Github's
#     zipballs have none), built with its Makefile (make EXE=bot; make arbiter). The
#     binary in Engines/ is a wrapper that runs the tree's bot with YGO_ROOT=<tree>,
#     so that "./Engines/<name> bench" works as for a UCI engine.
#   - The match runner is ygo-arbiter (the base engine's), not fastchess. An opening
#     is played twice, the seats swapped: a game pair. The arbiter prints its
#     cumulative pentanomial after each pair; the Client reports the differences.
#   - Books are JSON lines (one opening per line); each runner plays its slice.
#   - Instead of PGNs, the arbiter's records (one JSON line per game).

import bz2
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import zipfile

import requests

## Local imports must only use "import x", never "from x import ..."

import utils

# Engine names, as the arbiter labels them: the dev engine is the first bot
DEV, BASE = 'dev', 'base'

# A progress line or the final line of ygo-arbiter
PROGRESS = re.compile(
    r'games (\d+): \+(\d+) =(\d+) -(\d+) .*?penta \[(\d+), (\d+), (\d+), (\d+), (\d+)\]')

# The search's time per decision for "N=" and "NPS=" controls (the node limit decides)
NODES_TC = '60+1'

TIMEOUT_HTTP = 30

def github_repo(url):

    # "owner/repo" of a Github URL: https://github.com/o/r(.git), git@github.com:o/r(.git),
    # or an API URL https://api.github.com/repos/o/r/...

    match = re.search(r'github\.com[:/](?:repos/)?([^/]+)/([^/]+?)(?:\.git)?(?:/|$)', url)
    if not match:
        raise utils.OpenBenchBuildFailedException('Not a Github repository', url)
    return '%s/%s' % (match.group(1), match.group(2))

def download_zip(url, dest, headers=None):

    # Extract the archive at url into dest (the archive's single root folder's contents)

    response = requests.get(url, headers=headers, timeout=600)
    if response.status_code != 200:
        raise utils.OpenBenchBuildFailedException('Download failed', '%s: HTTP %d' % (url, response.status_code))

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, 'source.zip')
        with open(zip_path, 'wb') as fout:
            fout.write(response.content)
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            zip_file.extractall(temp_dir)
        root = [d for d in os.listdir(temp_dir) if d != 'source.zip'][0]
        shutil.move(os.path.join(temp_dir, root), dest)

def submodules(tree):

    # Paths and URLs of the tree's .gitmodules

    path = os.path.join(tree, '.gitmodules')
    if not os.path.exists(path):
        return []

    entries, current = [], {}
    for line in open(path):
        line = line.strip()
        if line.startswith('[submodule'):
            current = {}
            entries.append(current)
        elif '=' in line:
            key, value = [x.strip() for x in line.split('=', 1)]
            current[key] = value

    return [(e['path'], e['url']) for e in entries if 'path' in e and 'url' in e]

def fetch_submodules(tree, repo, sha, cache, headers=None):

    # Each submodule at the commit the tree's commit names (Github's contents API), from a
    # cache of extracted archives (Engines/submodules/<owner>-<repo>-<sha>), recursively

    for path, url in submodules(tree):

        api  = 'https://api.github.com/repos/%s/contents/%s?ref=%s' % (repo, path, sha)
        data = requests.get(api, headers=headers, timeout=TIMEOUT_HTTP).json()
        if data.get('type') != 'submodule':
            raise utils.OpenBenchBuildFailedException('Submodule not found', '%s: %s' % (path, data))

        sub_repo, sub_sha = github_repo(data.get('submodule_git_url') or url), data['sha']
        cached = os.path.join(cache, '%s-%s' % (sub_repo.replace('/', '-'), sub_sha))

        if not os.path.exists(cached):
            print('> Submodule %s: %s at %s' % (path, sub_repo, sub_sha[:10]))
            download_zip('https://github.com/%s/archive/%s.zip' % (sub_repo, sub_sha), cached + '.tmp')
            fetch_submodules(cached + '.tmp', sub_repo, sub_sha, cache, headers)
            os.rename(cached + '.tmp', cached)

        target = os.path.join(tree, path)
        if os.path.isdir(target):
            os.rmdir(target) # (an empty folder in the zipball)
        shutil.copytree(cached, target, symlinks=True)

def wrapper_script(tree):

    # The binary OpenBench sees: the tree's bot with YGO_ROOT=<tree>
    return '#!/bin/sh\nYGO_ROOT=%s exec %s "$@"\n' % (tree, os.path.join(tree, 'bot'))

def prepare_engine(engine, branch, source, out_path, private):

    # The engine's tree at <out_path>.root, built; out_path the wrapper. Returns its name.

    if os.path.isfile(out_path):
        print('Found [%s-%s]' % (engine, branch))
        return os.path.basename(out_path)

    headers = utils.read_git_credentials(engine) if private else None
    repo    = github_repo(source)
    sha     = source.rstrip('/').split('/')[-1]
    tree    = os.path.abspath(out_path + '.root')
    engines = os.path.dirname(os.path.abspath(out_path))

    print('Building [%s-%s]' % (engine, branch))
    if os.path.exists(tree):
        shutil.rmtree(tree)

    download_zip(source, tree, headers)
    fetch_submodules(tree, repo, sha, os.path.join(engines, 'submodules'), headers)

    # One cargo target directory for every build (incremental between commits)
    env = dict(os.environ, CARGO_TARGET_DIR=os.path.join(engines, 'target'))
    output = ''
    for target in (['make', '-j', 'EXE=%s' % os.path.join(tree, 'bot')],
                   ['make', 'arbiter', 'ARBITER=%s' % os.path.join(tree, 'ygo-arbiter')]):
        process = subprocess.run(target, cwd=tree, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output += process.stdout.decode('utf-8', errors='replace')
        if process.returncode:
            raise utils.OpenBenchBuildFailedException('Error during compilation', output)

    with open(out_path, 'w') as fout:
        fout.write(wrapper_script(tree))
    os.chmod(out_path, 0o755)

    return os.path.basename(out_path)

def engine_tree(name):
    return os.path.abspath(os.path.join('Engines', name + '.root'))

def book_slice(book_name, book_seed, start, count, out_path):

    # Openings [start, start + count) of the book in the order of book_seed (wrapping)

    with open(os.path.join('Books', book_name)) as fin:
        lines = [line for line in fin if line.strip()]

    order = list(range(len(lines)))
    random.Random(book_seed).shuffle(order)

    with open(out_path, 'w') as fout:
        for i in range(count):
            fout.write(lines[order[(start + i) % len(lines)]])

def search_settings(time_control, scale_factor):

    # (arbiter flags, bot environment) of an OpenBench time control

    if match := re.match(r'NPS=(\d+)$', time_control):
        return ['--tc', NODES_TC, '--nps-nodes', match.group(1)], {}

    if match := re.match(r'N=(\d+)$', time_control):
        return ['--tc', NODES_TC], { 'BOT_SEARCH_NODES' : match.group(1) }

    if match := re.match(r'(\d*(?:\.\d+)?)\+(\d*(?:\.\d+)?)$', time_control):
        base, inc = float(match.group(1)), float(match.group(2))
        return ['--tc', '%.3f+%.3f' % (base * scale_factor, inc * scale_factor)], {}

    raise utils.OpenBenchFatalWorkerException('Time control %s: ygo-arbiter takes NPS=, N= or BASE+INC' % time_control)

def bot_command(name, env):
    return ' '.join(['env'] + ['%s=%s' % kv for kv in sorted(env.items())] + [os.path.join(os.path.abspath('Engines'), name), 'alphabeta'])

def runner_command(workload, dev_name, base_name, scale_factor, book_path, records_path):

    test = workload['test']
    if test['dev']['time_control'] != test['base']['time_control']:
        raise utils.OpenBenchFatalWorkerException('ygo-arbiter plays both engines with one time control')

    flags, env = search_settings(test['dev']['time_control'], scale_factor)
    arbiter    = os.path.join(engine_tree(base_name), 'ygo-arbiter')

    return [arbiter,
        '--bot', '%s=%s' % (DEV , bot_command(dev_name , env)),
        '--bot', '%s=%s' % (BASE, bot_command(base_name, env)),
        '--book', book_path, '-n', str(workload['distribution']['rounds-per-runner']),
        '-c', str(workload['distribution']['concurrency-per']),
        '--records', records_path, '--report-every', '1'] + flags

def die_with_parent():

    # (in the arbiter's process before it starts: Linux kills it when the Client dies,
    # and its bots end with it; elsewhere nothing)

    try:
        import ctypes, signal
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
    except (OSError, AttributeError):
        pass

def runner_env(base_name):
    return dict(os.environ, YGO_ROOT=engine_tree(base_name))

def parse_progress(line):

    # (trinomial [L, D, W], pentanomial [LL, DL, DD/WL, DW, WW]) of a progress line, or None

    if not (match := PROGRESS.search(line)):
        return None

    wins, draws, losses = (int(match.group(i)) for i in (2, 3, 4))
    return [losses, draws, wins], [int(match.group(i)) for i in range(5, 10)]

def nps_stats(records_paths, scale_factor):

    # Nodes and search time (ms) of each engine's decisions, from the records' labels

    stats = { e : { 'nodes': 0, 'time': 0, 'time_scaled': 0 } for e in (DEV, BASE) }

    for path in records_paths:
        if not os.path.exists(path):
            continue
        for line in open(path):
            record = json.loads(line)
            agents = record.get('agents', [])
            for label in record.get('labels', []):
                engine = agents[label['player']] if label['player'] < len(agents) else None
                if engine in stats and 'nodes' in label and 'search_time' in label:
                    stats[engine]['nodes']       += label['nodes']
                    stats[engine]['time']        += label['search_time'] * 1000
                    stats[engine]['time_scaled'] += label['search_time'] * 1000 / scale_factor

    return stats

def compact_label(label):
    # (a label of the VERBOSE records: the eval in integer units and the times in ms)
    out = { k : label[k] for k in ('decision', 'player', 'depth', 'nodes') if k in label }
    if 'value' in label:
        out['value'] = round(label['value'])
    for key in ('time', 'search_time'):
        if key in label:
            out[key + '_ms'] = round(label[key] * 1000)
    return out

def compress_records(records_paths, mode):

    # COMPACT: the records without labels (the decks, seeds and responses replay a game),
    # about 0.55 KB per game; VERBOSE: with rounded labels, about 1.6 KB per game

    lines = []
    for path in records_paths:
        if not os.path.exists(path):
            continue
        for line in open(path):
            record = json.loads(line)
            labels = record.pop('labels', [])
            if mode == 'VERBOSE':
                record['labels'] = [compact_label(label) for label in labels]
            lines.append(json.dumps(record, separators=(',', ':')) + '\n')

    return bz2.compress(''.join(lines).encode('utf-8'))
