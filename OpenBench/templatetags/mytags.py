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

import django
import math
import re

import scipy.stats
import django.utils.safestring
import django.utils.timezone

import OpenBench.config
import OpenBench.models
import OpenBench.spsa_utils
import OpenBench.stats
import OpenBench.utils

def oneDigitPrecision(value):
    try:
        value = round(value, 1)
        if '.' not in str(value):
            return str(value) + '.0'
        pre, post = str(value).split('.')
        post += '0'
        return pre + '.' + post[0:1]
    except:
        return value

def twoDigitPrecision(value):
    try:
        value = round(value, 2)
        if '.' not in str(value):
            return str(value) + '.00'
        pre, post = str(value).split('.')
        post += '00'
        return pre + '.' + post[0:2]
    except:
        return value

def gitDiffLink(test):

    repo = OpenBench.utils.path_join(*test.dev.source.split('/')[:-2])
    repo = repo.replace('://api.github.com', '://github.com').replace('/repos/', '/')

    if test.test_mode == 'SPSA':
        return OpenBench.utils.path_join(repo, 'compare', test.dev.sha[:8])

    return OpenBench.utils.path_join(repo, 'compare',
        '{0}..{1}'.format(test.base.sha[:8], test.dev.sha[:8]))

def shortStatBlock(test):

    tri_line   = 'Games: %d W: %d L: %d D: %d' % test.as_nwld()
    penta_line = 'Ptnml(0-2): %d, %d, %d, %d, %d' % test.as_penta()

    if test.test_mode == 'SPSA':
        spsa_run = test.spsa_run # Avoid extra database accesses
        statlines = [
            'Tuning %d Parameters' % (spsa_run.parameters.count()),
            '%d/%d Iterations' % (test.games / (2 * spsa_run.pairs_per), spsa_run.iterations),
            '%d/%d Games Played' % (test.games, 2 * spsa_run.iterations * spsa_run.pairs_per)]

    elif test.test_mode == 'SPRT':
        llr_line = 'LLR: %0.2f (%0.2f, %0.2f) [%0.2f, %0.2f]' % (
            test.currentllr, test.lowerllr, test.upperllr, test.elolower, test.eloupper)
        statlines = [llr_line, tri_line, penta_line] if test.use_penta else [llr_line, tri_line]

    elif test.test_mode == 'GAMES':
        lower, elo, upper = OpenBench.stats.Elo(test.results())
        elo_line = 'Elo: %0.2f +- %0.2f (95%%) [N=%d]' % (elo, max(upper - elo, elo - lower), test.max_games)
        statlines = [elo_line, tri_line, penta_line] if test.use_penta else [elo_line, tri_line]

    elif test.test_mode == 'DATAGEN':
        status_line = 'Generated %d/%d Games' % (test.games, test.max_games)
        lower, elo, upper = OpenBench.stats.Elo(test.results())
        elo_line = 'Elo: %0.2f +- %0.2f (95%%) [N=%d]' % (elo, max(upper - elo, elo - lower), test.max_games)
        statlines = [status_line, elo_line, penta_line] if test.use_penta else [status_line, elo_line, tri_line]

    return '\n'.join(statlines)

def longStatBlock(test):

    assert test.test_mode != 'SPSA'

    threads     = int(OpenBench.utils.extract_option(test.dev_options, 'Threads'))
    hashmb      = int(OpenBench.utils.extract_option(test.dev_options, 'Hash'))
    timecontrol = test.dev_time_control + ['s', '']['=' in test.dev_time_control]
    type_text   = 'SPRT' if test.test_mode == 'SPRT' else 'Conf'

    lower, elo, upper = OpenBench.stats.Elo(test.results())

    lines = [
        'Elo   | %0.2f +- %0.2f (95%%)' % (elo, max(upper - elo, elo - lower)),
        '%-5s | %s Threads=%d Hash=%dMB' % (type_text, timecontrol, threads, hashmb),
    ]

    if test.test_mode == 'SPRT':
        lines.append('LLR   | %0.2f (%0.2f, %0.2f) [%0.2f, %0.2f]' % (
            test.currentllr, test.lowerllr, test.upperllr, test.elolower, test.eloupper))

    lines.append('Games | N: %d W: %d L: %d D: %d' % test.as_nwld())

    if test.use_penta:
        lines.append('Penta | [%d, %d, %d, %d, %d]' % test.as_penta())

    return '\n'.join(lines)

def testResultColour(test):

    if test.passed:
        if test.elolower + test.eloupper < 0: return 'blue'
        return 'green'
    if test.failed:
        if test.wins >= test.losses: return 'yellow'
        return 'red'
    return ''

def sumAttributes(iterable, attribute):
    try: return sum([getattr(f, attribute) for f in iterable])
    except: return 0

def insertCommas(value):
    return '{:,}'.format(int(value))

def prettyName(name):
    if re.search('^[0-9a-fA-F]{40}$', name):
        return name[:16].upper()
    return name

def prettyDevName(test):

    # If engines are different, use the base name + branch
    if test.dev_engine != test.base_engine:
        return '[%s] %s' % (test.base_engine, test.base.name)

    # If testing different Networks, possibly use the Network name
    if test.dev.name == test.base.name and test.dev_netname != '':

        # Nets match as well, so revert back to the branch name
        if test.dev_network == test.base_network:
            return prettyName(test.dev.name)

        # Use the network's name, if we still have it saved
        try: return OpenBench.models.Network.objects.get(sha256=test.dev_network).name
        except: return test.dev_netname # File has since been deleted ?

    return prettyName(test.dev.name)

def testIdToPrettyName(test_id):
    return prettyName(OpenBench.models.Test.objects.get(id=test_id).dev.name)

def testIdToTimeControl(test_id):
    return OpenBench.models.Test.objects.get(id=test_id).dev_time_control

def cpuflagsBlock(machine, N=8):

    reported = []
    flags    = machine.info['cpu_flags']

    general_flags   = ['BMI2', 'POPCNT']
    broad_avx_flags = ['AVX2', 'AVX', 'SSE42', 'SSE41', 'SSSE3']

    for flag in general_flags:
        if flag in flags:
            reported.append(flag)
            break

    for flag in broad_avx_flags:
        if flag in flags:
            reported.append(flag)
            break

    for flag in flags:
        if flag not in general_flags and flag not in broad_avx_flags:
            reported.append(flag)

    return ' '.join(reported)

def compilerBlock(machine):
    string = ''
    for engine, info in machine.info['compilers'].items():
        string += '%-16s %-8s (%s)\n' % (engine, info[0], info[1])
    return string

def removePrefix(value, prefix):
    return value.removeprefix(prefix)

def machine_name(machine_id):
    try:
        machine = OpenBench.models.Machine.objects.get(id=machine_id)
        return machine.info['machine_name']
    except: return 'None'


register = django.template.Library()
register.filter('oneDigitPrecision', oneDigitPrecision)
register.filter('twoDigitPrecision', twoDigitPrecision)
register.filter('gitDiffLink', gitDiffLink)
register.filter('shortStatBlock', shortStatBlock)
register.filter('longStatBlock', longStatBlock)
register.filter('testResultColour', testResultColour)
register.filter('sumAttributes', sumAttributes)
register.filter('insertCommas', insertCommas)
register.filter('prettyName', prettyName)
register.filter('prettyDevName', prettyDevName)
register.filter('testIdToPrettyName', testIdToPrettyName)
register.filter('testIdToTimeControl', testIdToTimeControl)
register.filter('cpuflagsBlock', cpuflagsBlock)
register.filter('compilerBlock', compilerBlock)
register.filter('removePrefix', removePrefix)
register.filter('machine_name', machine_name)

def book_download_link(workload):
    if (book := OpenBench.models.Book.objects.filter(name=workload.book_name).first()):
        return book.source

def network_download_link(workload, branch):

    assert branch in [ 'dev', 'base' ]

    sha    = workload.dev_network if branch == 'dev' else workload.base_network
    engine = workload.dev_engine  if branch == 'dev' else workload.base_engine

    # Network could have been deleted after this workload was finished
    if (network := OpenBench.models.Network.objects.filter(sha256=sha, engine=engine).first()):
        return '/networks/%s/download/%s/' % (engine, sha)

    return '/networks/%s/' % (engine)

def workload_url(workload):

    # Might be a workload id
    if type(workload) == int:
        workload = OpenBench.models.Test.objects.get(id=workload)

    # Differentiate between Tunes, Datagen, and regular Tests
    mapping = { 'SPSA' : 'tune', 'DATAGEN' : 'datagen' }
    return '/%s/%d/' % (mapping.get(workload.test_mode, 'test'), workload.id)

def workload_pretty_name(workload):

    # Might be a workload id
    if type(workload) == int:
        workload = OpenBench.models.Test.objects.get(id=workload)

    # Convert commit sha's to just the first 16 characters
    if re.search('^[0-9a-fA-F]{40}$', workload.dev.name):
        return workload.dev.name[:16].lower()

    return workload.dev.name

def git_diff_text(workload, N=24):

    dev_name = workload.dev.name
    dev_name = dev_name[:N] + '...' if len(dev_name) > N else dev_name

    base_name = workload.base.name
    base_name = base_name[:N] + '...' if len(base_name) > N else base_name

    return '%s vs %s' % (dev_name, base_name)


def test_is_smp_odds(test):
    dev_threads  = int(OpenBench.utils.extract_option(test.dev_options , 'Threads'))
    base_threads = int(OpenBench.utils.extract_option(test.base_options, 'Threads'))
    return dev_threads != base_threads

def test_is_time_odds(test):
    return test.dev_time_control != test.base_time_control \
       and not OpenBench.utils.TimeControl.is_nps_adjusted_pair(test.dev_time_control, test.base_time_control)

def test_is_fischer(test):
    return 'FRC' in test.book_name.upper() or '960' in test.book_name.upper()

register.filter('book_download_link', book_download_link)
register.filter('network_download_link', network_download_link)

register.filter('workload_url', workload_url)
register.filter('workload_pretty_name', workload_pretty_name)

register.filter('git_diff_text', git_diff_text)

register.filter('test_is_smp_odds'  , test_is_smp_odds  )
register.filter('test_is_time_odds' , test_is_time_odds )
register.filter('test_is_fischer'   , test_is_fischer   )


@register.filter
def next(iterable, index):
    try: return iterable[int(index) + 1]
    except: return None

@register.filter
def previous(iterable, index):
    try: return iterable[int(index) - 1]
    except: return None

@register.filter
def eloDistribution(test):

    # An inline SVG: the distribution of the true Elo (uniform prior, as the Elo line of the stat
    # block), with the SPRT bounds (or 0) and the probabilities above them. Empty without games.

    if not (posterior := OpenBench.stats.EloPosterior(test.results())):
        return ''
    mu, sd = posterior

    lo = OpenBench.stats.logistic_elo(max(mu - 4 * sd, 1e-3))
    hi = OpenBench.stats.logistic_elo(min(mu + 4 * sd, 1 - 1e-3))
    marks = [test.elolower, test.eloupper] if test.test_mode == 'SPRT' else [0.0]
    lo, hi = min([lo] + marks) - 1, max([hi] + marks) + 1

    # (the density over Elo: the score's normal density times d score / d Elo)
    W, H, top, base = 400, 120, 8, 96
    def density(elo):
        s = OpenBench.stats.logistic_score(elo)
        return scipy.stats.norm.pdf((s - mu) / sd) / sd * s * (1 - s) * math.log(10) / 400
    xs   = [lo + (hi - lo) * i / 200 for i in range(201)]
    ys   = [density(x) for x in xs]
    peak = max(ys)
    X    = lambda elo: (elo - lo) / (hi - lo) * W
    Y    = lambda y: base - y / peak * (base - top)
    path = 'M%.1f,%.1f ' % (X(xs[0]), base) + ' '.join('L%.1f,%.1f' % (X(x), Y(y)) for x, y in zip(xs, ys)) + ' L%.1f,%.1f Z' % (X(xs[-1]), base)

    parts = ['<path d="%s" fill="currentColor" fill-opacity="0.18" stroke="currentColor" stroke-width="1.5"/>' % path,
             '<line x1="0" y1="%d" x2="%d" y2="%d" stroke="currentColor" stroke-opacity="0.5"/>' % (base, W, base)]
    labels = []
    for elo in marks:
        p = OpenBench.stats.prob_elo_above(posterior, elo)
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="currentColor" stroke-dasharray="3 3"/>' % (X(elo), top, X(elo), base))
        parts.append('<text x="%.1f" y="%d" font-size="11" text-anchor="middle" fill="currentColor">%g</text>' % (X(elo), base + 13, elo))
        labels.append('P(Elo &gt; %g) = %.1f%%' % (elo, 100 * p))

    if eta := testEta(test):
        labels.append(eta)

    title = 'Elo distribution (uniform prior): ' + ', '.join(labels)
    return django.utils.safestring.mark_safe(
        '<figure class="elo-distribution">'
        '<svg viewBox="0 0 %d %d" width="100%%" style="max-width: %dpx; display: block" role="img" aria-label="%s">%s</svg>'
        '<figcaption style="font-size: 0.85em">%s</figcaption></figure>' % (W, H, W, title, ''.join(parts), ' &middot; '.join(labels)))

def eta_estimate(test):

    # (games left, the hypothesis it moves to or None, games per second) of a running test: the
    # games left (SPRT: the LLR at its rate per game so far to the bound it moves to; GAMES: to
    # max_games), the speed since its first results. None if finished, without a start time, or
    # the LLR has no direction yet.

    if test.finished or not test.started or not test.games:
        return None

    if test.test_mode == 'SPRT':
        rate = test.currentllr / test.games
        if abs(rate) < 1e-9:
            return None
        bound = test.upperllr if rate > 0 else test.lowerllr
        left  = max(0.0, (bound - test.currentllr) / rate)
        towards = 'H1' if rate > 0 else 'H0'
    elif test.test_mode == 'GAMES':
        left, towards = max(0, test.max_games - test.games), None
    else:
        return None

    seconds = (django.utils.timezone.now() - test.started).total_seconds()
    if seconds <= 0 or left <= 0:
        return None
    return left, towards, test.games / seconds

def format_duration(seconds):
    hours = seconds / 3600
    return '%.0f min' % (seconds / 60) if hours < 1 else '%.1f h' % hours if hours < 48 \
        else '%.0f days' % (hours / 24) if hours < 168 else '> 1 week'

def testEta(test):

    # "ETA ~ ..." of a running test (eta_estimate)

    if not (estimate := eta_estimate(test)):
        return None
    left, towards, speed = estimate
    return 'ETA ~ %s (~%s games%s)' % (
        format_duration(left / speed), '{:,}'.format(int(round(left, -2))), ' to ' + towards if towards else '')

def queueEta(tests):

    # "ETA ~ ... for all" of the active tests: their games left over the sum of their speeds (tests
    # that share the workers each have a part of the speed), "+N without an estimate" for the tests
    # without one (no results or no direction yet). Empty without any estimate.

    estimates = [eta_estimate(test) for test in tests]
    known     = [e for e in estimates if e]
    if not known:
        return ''
    text = 'ETA ~ %s for all' % format_duration(sum(e[0] for e in known) / sum(e[2] for e in known))
    if unknown := len(estimates) - len(known):
        text += ' (+%d without an estimate)' % unknown
    return text
