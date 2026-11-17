function copy_text(text) {

    var area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();

    try {
        document.execCommand("copy");
        document.body.removeChild(area);
    }

    catch (err) {
        document.body.removeChild(area);
        console.error("Unable to copy to Clipboard");
    }
}

function copy_text_from_element(element_id, keep_url) {

    var text = document.getElementById(element_id).innerHTML;
    text = text.replace(/<br>/g, "\n");

    if (keep_url)
        text += "\n" + window.location.href;

    copy_text(text);
}


function populate_results(results) {

    const container = document.getElementById('results-container');

    container.innerHTML = ''; // Clear everything for sanity

    results.forEach(result => {
        const tr = document.createElement('tr');

        // Highlight active rows
        if (result.active) tr.classList.add('active-highlight');

        // Collapse the trinomial won/lost/drawn into the pentanomial tuple and
        // its pair count, mirroring the aggregate summary tables above
        const penta = [result.LL, result.LD, result.DD, result.DW, result.WW];
        const pairs = penta.reduce((a, b) => a + b, 0);

        tr.innerHTML = `
            <td><a href="/machines/${result.machine__id}">${result.machine__id}</a></td>
            <td>${result.machine__user__username.charAt(0).toUpperCase() + result.machine__user__username.slice(1)}</td>
            <td class="numeric">${result.games}</td>
            <td>(${penta.join(', ')})</td>
            <td class="numeric">${pairs}</td>
            <td class="numeric">${result.timeloss}</td>
            <td class="numeric">${result.crashes}</td>
        `;

        container.appendChild(tr);
    });
}

async function fetch_results(workload_id) {
    fetch(`/api/workload/${workload_id}/results/`)
        .then(r => r.json())
        .then(data => populate_results(data.results))
}


function summary_cell(tag, text, class_name) {

    // Keys are free-form (cpu names, isa names), so set everything as text to
    // avoid injecting any markup a Machine might have reported
    const cell = document.createElement(tag);
    cell.textContent = text;
    if (class_name) cell.className = class_name;
    return cell;
}

function format_cpu_name(name) {

    // CPU names as reported by py-cpuinfo can be verbose and noisy.
    // Clean them up here so the table stays readable.

    // Drop the (R) registered-trademark marker.
    name = name.replace(/\(R\)/g, '');

    // "Intel Xeon" is redundant — Xeon already implies Intel, so drop Intel.
    if (/Intel/.test(name) && /Xeon/.test(name))
        name = name.replace(/Intel/g, '');

    // Likewise, "AMD EPYC" and "AMD Ryzen" are redundant — both imply AMD.
    if (/AMD/.test(name) && /EPYC|Ryzen/.test(name))
        name = name.replace(/AMD/g, '');

    // "Processor" and "CPU" add nothing in this context.
    name = name.replace(/Processor/g, '');
    name = name.replace(/CPU/g, '');

    // Core counts, ie "16-Core", are reported separately in the table.
    name = name.replace(/\d+-Core/gi, '');

    // The removals above can leave stray spacing; collapse runs of whitespace
    // to a single space and trim the ends.
    name = name.replace(/\s+/g, ' ').trim();

    return name;
}

function append_summary_section(table, label, rows, key_formatter) {

    // Older workloads don't have NPS tracking stats.
    const is_nps_available =  rows.some(row => row.dev_nps > 0);

    // A header row naming the grouping, then one tbody of data rows. All three
    // sections share the one table, so their columns line up automatically.
    const header = document.createElement('tr');
    header.className = 'table-header';
    header.appendChild(summary_cell('th', label));

    ['Penta', 'Elo', 'Pairs', '%'].forEach(name => {
        header.appendChild(summary_cell('th', name));
    });

    if (is_nps_available) {
        header.appendChild(summary_cell('th', 'KNPS'));
        header.appendChild(summary_cell('th', 'Scaled KNPS'));
    }

    table.appendChild(header);

    const tbody = document.createElement('tbody');

    rows.forEach(row => {
        const tr = document.createElement('tr');

        // The API hands us display-ready fields: the penta tuple as a string,
        // a point-estimate Elo, the pair count, and the % of the group total
        tr.appendChild(summary_cell('td', key_formatter ? key_formatter(row.key) : row.key));
        tr.appendChild(summary_cell('td', row.penta));
        tr.appendChild(summary_cell('td', row.elo,   'numeric'));
        tr.appendChild(summary_cell('td', row.pairs, 'numeric'));
        tr.appendChild(summary_cell('td', row.percent, 'numeric'));

        if (is_nps_available) {
            const format_nps = (nps) => (nps / 1000.0).toFixed(1);

            tr.appendChild(summary_cell('td', `${format_nps(row.dev_nps)} / ${format_nps(row.base_nps)}`));
            tr.appendChild(summary_cell('td', `${format_nps(row.dev_nps_scaled)} / ${format_nps(row.base_nps_scaled)}`));
        }

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
}

async function fetch_summary(workload_id) {
    fetch(`/api/workload/${workload_id}/summary/`)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('summary-container');
            container.innerHTML = ''; // Rebuild the whole table each fetch

            const table = document.createElement('table');
            table.className = 'stripes wrappable summary-table';

            append_summary_section(table, 'User', data.summary.user);
            append_summary_section(table, 'CPU',  data.summary.cpu_name, format_cpu_name);
            append_summary_section(table, 'ISA',  data.summary.isa_name);

            container.appendChild(table);
        })
}


async function copy_spsa_inputs(workload_id) {
    const resp = await fetch(`/api/spsa/${workload_id}/inputs/`)
    const text = await resp.text()
    copy_text(text)
}

async function copy_spsa_outputs(workload_id) {
    const resp = await fetch(`/api/spsa/${workload_id}/outputs/`)
    const text = await resp.text()
    copy_text(text)
}

async function fetch_spsa_digest(workload_id) {
    const resp  = await fetch(`/api/spsa/${workload_id}/digest/`)
    const text  = await resp.text()
    const lines = text.trim().split('\n')

    // Skip the header line (index 0) and process data rows
    const tbody = document.getElementById('spsa-digest-body-container')
    tbody.innerHTML = ''

    for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',')
        const tr = document.createElement('tr')

        values.forEach(value => {
            const td = document.createElement('td')
            td.textContent = value
            tr.appendChild(td)
        })

        tbody.appendChild(tr)
    }

    // Show the data and hide the button
    tbody.style.display = ''
    const buttonContainer = document.getElementById('spsa-digest-button-container')
    buttonContainer.style.display = 'none'
}

// SPSA history: one small chart per parameter, its value over the iterations (x: 0 to the
// tune's iterations; y: the range of the values, the start included). Hover: the values at
// that iteration in every chart.
async function fetch_spsa_history(workload_id) {
    const resp = await fetch(`/api/spsa/${workload_id}/history/`)
    const data = await resp.json()
    if (data.history)
        draw_spsa_history(data.history)
}

function draw_spsa_history(h) {

    const W = 300, H = 90
    const svg_ns    = 'http://www.w3.org/2000/svg'
    const grid      = document.getElementById('spsa-history-grid')
    const caption   = document.getElementById('spsa-history-caption')
    const per_iter  = 2 * h.pairs_per
    const iters     = h.points.map(p => p.games / per_iter)
    const x_of      = it => W * it / h.iterations
    const fmt       = (p, v) => p.is_float ? v.toPrecision(4) : v.toFixed(2)

    const make = (tag, attrs) => {
        const e = document.createElementNS(svg_ns, tag)
        for (const k in attrs) e.setAttribute(k, attrs[k])
        return e
    }

    grid.innerHTML = ''
    const charts = h.params.map((p, i) => {

        const values = h.points.map(pt => pt.values[i])
        let lo = Math.min(p.start, ...values), hi = Math.max(p.start, ...values)
        if (hi - lo < 1e-9) { lo -= 0.5; hi += 0.5 }
        const pad  = (hi - lo) * 0.08
        lo -= pad; hi += pad
        const y_of = v => H * (hi - v) / (hi - lo)

        const cell  = document.createElement('div')
        cell.className = 'spsa-chart'
        const title = document.createElement('div')
        title.className = 'spsa-chart-title'
        const name  = document.createElement('span')
        name.textContent = p.name
        const value = document.createElement('span')
        value.className = 'spsa-chart-value'
        title.append(name, value)

        const svg = make('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' })
        svg.append(make('line', { class: 'spsa-start', x1: 0, x2: W, y1: y_of(p.start), y2: y_of(p.start) }))
        svg.append(make('polyline', { class: 'spsa-line',
            points: values.map((v, j) => `${x_of(iters[j]).toFixed(2)},${y_of(v).toFixed(2)}`).join(' ') }))
        const cross = make('line', { class: 'spsa-cross', y1: 0, y2: H, visibility: 'hidden' })
        const dot   = make('line', { class: 'spsa-dot', visibility: 'hidden' })
        svg.append(cross, dot)

        const axis = document.createElement('div')
        axis.className = 'spsa-chart-axis'
        axis.innerHTML = `<span>${fmt(p, hi - pad)}</span><span>${fmt(p, lo + pad)}</span>`

        const body = document.createElement('div')
        body.className = 'spsa-chart-body'
        body.append(svg, axis)
        cell.append(title, body)
        grid.append(cell)

        return { p, values, value, cross, dot, y_of }
    })

    const show = j => {
        const at = j === null ? h.points.length - 1 : j
        for (const c of charts) {
            const v = c.values[at]
            c.value.textContent = `${fmt(c.p, v)} (start ${fmt(c.p, c.p.start)})`
            const x = x_of(iters[at]), y = c.y_of(v)
            for (const [e, a] of [[c.cross, { x1: x, x2: x }], [c.dot, { x1: x, x2: x, y1: y, y2: y }]]) {
                for (const k in a) e.setAttribute(k, a[k])
                e.setAttribute('visibility', j === null ? 'hidden' : 'visible')
            }
        }
        const it = Math.round(iters[at])
        caption.textContent = j === null
            ? `Iteration ${it} of ${h.iterations} (${h.points.length - 1} snapshots). Dashed: start value. Hover for the values at an iteration.`
            : `Iteration ${it} of ${h.iterations} (${h.points[at].games} games)`
    }

    // The nearest snapshot to the pointer, from any chart
    grid.onpointermove = ev => {
        const svg = ev.target.closest('svg')
        if (!svg) return show(null)
        const r  = svg.getBoundingClientRect()
        const it = h.iterations * (ev.clientX - r.left) / r.width
        let best = 0
        iters.forEach((x, j) => { if (Math.abs(x - it) < Math.abs(iters[best] - it)) best = j })
        show(best)
    }
    grid.onpointerleave = () => show(null)
    show(null)
}
