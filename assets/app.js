const state = { all: [], filtered: [] };
const els = {
  cards: document.querySelector('#cards'),
  empty: document.querySelector('#empty-state'),
  search: document.querySelector('#search'),
  project: document.querySelector('#filter-project'),
  location: document.querySelector('#filter-location'),
  service: document.querySelector('#filter-service'),
  count: document.querySelector('#result-count'),
  updated: document.querySelector('#updated-at'),
  dialog: document.querySelector('#equipment-dialog'),
  dialogContent: document.querySelector('#dialog-content'),
  dialogClose: document.querySelector('#dialog-close')
};

const norm = (v='') => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
const safe = (v='') => String(v ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const display = (v, fallback='No especificado') => v && String(v).trim() ? String(v).trim() : fallback;
const serviceYes = v => ['si','sí','yes','true','1'].includes(norm(v));

function addOptions(select, values) {
  [...new Set(values.filter(Boolean).map(v => String(v).trim()))]
    .sort((a,b) => a.localeCompare(b,'es',{sensitivity:'base'}))
    .forEach(value => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
}

function imageHTML(item, className='') {
  if (item.foto) return `<img class="${className}" src="${safe(item.foto)}" alt="Fotografía de ${safe(item.equipo)}" loading="lazy">`;
  const initial = display(item.equipo,'E').charAt(0).toUpperCase();
  return `<div class="media-fallback" aria-label="Equipo sin fotografía">${safe(initial)}</div>`;
}

function card(item) {
  const projectBadge = item.codigo_proyecto || 'Proyecto de investigación';
  return `
    <article class="equipment-card">
      <div class="card-media">
        ${imageHTML(item)}
        <span class="card-badge" title="${safe(projectBadge)}">${safe(projectBadge)}</span>
      </div>
      <div class="card-body">
        <p class="card-kicker">${safe(item.institucion || 'UNPHU')}</p>
        <h3 class="card-title">${safe(display(item.equipo))}</h3>
        <p class="card-desc">${safe(display(item.descripcion))}</p>
        <div class="meta-list">
          <div class="meta-row"><b>Serie</b><span>${safe(display(item.serie,'No registrada'))}</span></div>
          <div class="meta-row"><b>Ubicación</b><span>${safe(display(item.ubicacion))}</span></div>
          <div class="meta-row"><b>Proyecto</b><span>${safe(display(item.proyecto))}</span></div>
        </div>
        <div class="card-footer">
          <span class="status-pill">${safe(display(item.funcionamiento,'Estado no indicado'))}</span>
          <button class="details-btn" data-id="${safe(item.id)}">Ver ficha →</button>
        </div>
      </div>
    </article>`;
}

function render() {
  const q = norm(els.search.value);
  const project = els.project.value;
  const location = els.location.value;
  const service = els.service.value;
  state.filtered = state.all.filter(item => {
    const haystack = norm([item.equipo,item.descripcion,item.serie,item.proyecto,item.codigo_proyecto,item.ubicacion,item.funcionamiento,item.institucion].join(' '));
    if (q && !haystack.includes(q)) return false;
    if (project && item.proyecto !== project) return false;
    if (location && item.ubicacion !== location) return false;
    if (service === 'si' && !serviceYes(item.servicio_externo)) return false;
    if (service === 'no' && serviceYes(item.servicio_externo)) return false;
    return true;
  });
  els.cards.innerHTML = state.filtered.map(card).join('');
  els.count.textContent = `Mostrando ${state.filtered.length} de ${state.all.length} equipos`;
  els.empty.hidden = state.filtered.length !== 0;
  els.cards.hidden = state.filtered.length === 0;
}

function openDialog(id) {
  const item = state.all.find(x => x.id === id);
  if (!item) return;
  els.dialogContent.innerHTML = `
    <div class="dialog-grid">
      <div class="dialog-image">${imageHTML(item)}</div>
      <div class="dialog-data">
        <p class="eyebrow dark">${safe(item.codigo_proyecto || item.institucion || 'Ficha del equipo')}</p>
        <h2>${safe(display(item.equipo))}</h2>
        <p class="lead">${safe(display(item.descripcion))}</p>
        <div class="detail-grid">
          <div class="detail-item"><span>Número de serie</span><strong>${safe(display(item.serie,'No registrada'))}</strong></div>
          <div class="detail-item"><span>Institución</span><strong>${safe(display(item.institucion))}</strong></div>
          <div class="detail-item full"><span>Proyecto</span><strong>${safe(display(item.proyecto))}</strong></div>
          <div class="detail-item"><span>Ubicación</span><strong>${safe(display(item.ubicacion))}</strong></div>
          <div class="detail-item"><span>Funcionamiento</span><strong>${safe(display(item.funcionamiento))}</strong></div>
          <div class="detail-item"><span>Servicio a otra institución</span><strong>${safe(display(item.servicio_externo))}</strong></div>
          <div class="detail-item"><span>Fuente</span><strong>${safe(display(item.fuente))}</strong></div>
        </div>
      </div>
    </div>`;
  els.dialog.showModal();
}

async function init() {
  try {
    const response = await fetch(`data/equipos.json?v=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.all = payload.equipos || [];
    addOptions(els.project, state.all.map(x => x.proyecto));
    addOptions(els.location, state.all.map(x => x.ubicacion));
    document.querySelector('#stat-equipos').textContent = state.all.length.toLocaleString('es-DO');
    document.querySelector('#stat-proyectos').textContent = new Set(state.all.map(x=>x.proyecto).filter(Boolean)).size.toLocaleString('es-DO');
    document.querySelector('#stat-ubicaciones').textContent = new Set(state.all.map(x=>x.ubicacion).filter(Boolean)).size.toLocaleString('es-DO');
    document.querySelector('#stat-servicio').textContent = state.all.filter(x=>serviceYes(x.servicio_externo)).length.toLocaleString('es-DO');
    const when = payload.generado_en ? new Date(payload.generado_en) : null;
    els.updated.textContent = `Actualizado desde Excel: ${when && !Number.isNaN(when.getTime()) ? when.toLocaleString('es-DO',{dateStyle:'medium',timeStyle:'short'}) : 'fecha no disponible'}`;
    render();
  } catch (err) {
    console.error(err);
    els.count.textContent = 'No se pudo cargar el catálogo.';
    els.cards.innerHTML = `<div class="empty-state"><strong>Error al cargar data/equipos.json</strong><span>Ejecuta el generador antes de publicar el sitio.</span></div>`;
  }
}

[els.search,els.project,els.location,els.service].forEach(el => el.addEventListener('input', render));
els.cards.addEventListener('click', e => { const b=e.target.closest('[data-id]'); if (b) openDialog(b.dataset.id); });
els.dialogClose.addEventListener('click', () => els.dialog.close());
els.dialog.addEventListener('click', e => { if (e.target === els.dialog) els.dialog.close(); });
init();
