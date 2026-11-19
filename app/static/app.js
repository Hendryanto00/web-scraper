/* Scraper workspace: FastAPI remains the source of extracted data.
 * Reviews and job metadata belong only to this browser session. */
'use strict';
const get = id => document.getElementById(id);
const icon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const KEY = 'scraper-workspace-v2';
const defaults = () => ({jobs: [], current: null, reviews: {}, operator: 'Operator lokal', pageSize: 10, firstRowHeader: true});
let state = defaults();
try {
  const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
  if (saved && Array.isArray(saved.jobs)) {
    state.jobs = saved.jobs.slice(0, 20);
    state.current = saved.current && Array.isArray(saved.current.tables) && Array.isArray(saved.current.links) && typeof saved.current.text === 'string' ? saved.current : null;
    state.reviews = saved.reviews && typeof saved.reviews === 'object' ? saved.reviews : {};
    state.operator = typeof saved.operator === 'string' ? saved.operator.slice(0, 40) : state.operator;
    state.pageSize = [10,25,50].includes(saved.pageSize) ? saved.pageSize : 10;
    state.firstRowHeader = saved.firstRowHeader !== false;
  }
} catch { /* Fresh session if browser storage is unavailable or invalid. */ }
let currentView = 'dashboard';
let busy = false;
let manualToken = null;
let tableIndex = 0;
let firstRowHeader = state.firstRowHeader;
let pageNumber = 1;
let query = '';
let reviewFilter = 'all';
let toastTimer;
const viewInfo = {
  dashboard: ['Dashboard','Pantau pengambilan dan pemeriksaan data dalam satu workspace.'],
  certificates: ['Data hasil scraping','Telusuri tabel hasil ekstraksi untuk pemeriksaan data sumber.'],
  scraping: ['Proses scraping','Ambil data dari URL dan periksa hasil ekstraksinya.'],
  history: ['Riwayat scraping','Lacak proses, waktu pengambilan, dan pesan kegagalan.'],
  verification: ['Verifikasi data','Tinjau hasil sumber dan tandai pemeriksaan manual operator.'],
  settings: ['Pengaturan','Atur preferensi tampilan workspace lokal.'],
  guide: ['Panduan penggunaan','Langkah operasional dan bantuan pengambilan data.']
};
function icons() { if (window.lucide) window.lucide.createIcons({attrs: {'aria-hidden':'true'}}); }
function persist() {
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); get('storage-notice').hidden = true; }
  catch {
    // Keep small job metadata even when the latest result exceeds browser quota.
    try { sessionStorage.setItem(KEY, JSON.stringify({...state, current:null, reviews:{}})); } catch { /* In-memory state remains usable. */ }
    get('storage-notice').hidden = false;
    get('storage-notice').textContent = 'Hasil aktif hanya tersedia di memori karena penyimpanan browser penuh/tidak tersedia. Unduh JSON sebelum memuat ulang halaman.';
  }
}
function toast(message) { clearTimeout(toastTimer); get('toast').textContent = message; get('toast').hidden = false; toastTimer = setTimeout(() => get('toast').hidden = true, 4500); }
function downloadJSON(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value,null,2)], {type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function timeLabel(value, withDate=false) {
  return new Intl.DateTimeFormat('id-ID', {timeZone:'Asia/Jakarta', ...(withDate ? {day:'2-digit',month:'short'} : {}), hour:'2-digit',minute:'2-digit'}).format(new Date(value)) + ' WIB';
}
function hostname(url) { try { return new URL(url).hostname; } catch { return url; } }
function safeLink(url, text) {
  const link = document.createElement('a'); link.textContent = text; link.dataset.userContent='';
  try { const parsed = new URL(url); if (['http:','https:'].includes(parsed.protocol)) { link.href = parsed.href; link.target = '_blank'; link.rel='noopener noreferrer'; } } catch { /* Plain text only. */ }
  return link;
}
const reviewMeta = {
  pending: ['Belum diperiksa','neutral-soft'],
  reviewed: ['Sudah diperiksa','green-soft'],
  correction: ['Perlu perbaikan','amber-soft']
};
function badge(label, style) { return `<span class="badge ${style}">${escapeHTML(label)}</span>`; }
function getRows() {
  const table = state.current?.tables[tableIndex] || [];
  return table.slice(firstRowHeader ? 1 : 0).map((cells,index) => {
    const rawIndex = index + (firstRowHeader ? 1 : 0);
    const id = `${tableIndex}:${rawIndex}`;
    return {id, rawIndex, cells, status: reviewMeta[state.reviews[id]] ? state.reviews[id] : 'pending'};
  });
}
function allRecordCount() { return state.current?.tables.reduce((sum, rows) => sum + Math.max(0, rows.length - (firstRowHeader ? 1 : 0)), 0) || 0; }
function updateProfile() {
  document.querySelector('.profile-name').textContent = state.operator;
  document.querySelector('#profile-menu strong').textContent = state.operator;
  document.querySelector('.avatar').textContent = state.operator.trim().split(/\s+/).map(part => part[0]).join('').slice(0,2).toUpperCase() || 'OP';
  get('operator-name').value = state.operator; get('page-size').value = String(state.pageSize);
}
function setMobileMenu(open) {
  get('sidebar').classList.toggle('open',open); get('sidebar-overlay').hidden = !open;
  get('sidebar').inert = !open && window.innerWidth <= 760;
  get('menu-toggle').setAttribute('aria-expanded',String(open));
  get('menu-toggle').setAttribute('aria-label',open ? 'Tutup navigasi' : 'Buka navigasi');
  document.body.style.overflow = open ? 'hidden' : '';
  if (open) get('sidebar-close').focus();
}
function navigate() {
  const hash = location.hash.slice(1);
  const aliases = {workspace:'scraping',panduan:'guide'};
  currentView = viewInfo[hash] ? hash : (aliases[hash] || 'dashboard');
  document.querySelectorAll('[data-view]').forEach(section => section.hidden = section.dataset.view !== currentView);
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === currentView;
    link.classList.toggle('active',active);
    if (active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  });
  const [title,description] = viewInfo[currentView];
  get('page-title').textContent = title; get('page-description').textContent = description;
  get('breadcrumb-current').textContent = title; document.title = `${title} · Scraper`;
  const actions = get('page-actions'); actions.replaceChildren();
  if (['dashboard','certificates','history','verification'].includes(currentView)) {
    actions.innerHTML = `<a class="button secondary" href="#guide">${icon('book-open')}Panduan</a><a class="button primary" href="#scraping">${icon('plus')}Scraping baru</a>`;
  } else if (currentView === 'scraping') actions.innerHTML = `<a class="button secondary" href="#history">${icon('history')}Riwayat proses</a>`;
  setMobileMenu(false); get('profile-menu').hidden = true; get('profile-button').setAttribute('aria-expanded','false');
  if (currentView === 'certificates' || currentView === 'verification') { query=''; pageNumber=1; reviewFilter=currentView === 'verification' ? 'pending' : 'all'; renderDataWorkspace(); }
  if (currentView === 'history') renderHistory();
  renderDashboard(); icons();
  window.scrollTo({top:0,behavior:'instant'});
}
function renderDashboard() {
  const total = allRecordCount();
  const statuses = Object.entries(state.reviews).filter(([key]) => {
    const [ti,ri] = key.split(':').map(Number);
    return state.current?.tables[ti]?.[ri] && ri >= (firstRowHeader ? 1 : 0);
  }).map(([,value]) => value);
  const reviewed = statuses.filter(value => value === 'reviewed').length;
  const correction = statuses.filter(value => value === 'correction').length;
  get('metric-records').textContent = total.toLocaleString('id-ID'); get('metric-pending').textContent = Math.max(0,total-reviewed-correction).toLocaleString('id-ID');
  get('metric-reviewed').textContent = reviewed.toLocaleString('id-ID'); get('metric-jobs').textContent=state.jobs.length;
  const successes = state.jobs.filter(job => job.status === 'success').length;
  get('metric-job-note').textContent = state.jobs.length ? `${successes} berhasil · ${state.jobs.length-successes} gagal` : 'Belum ada proses';
  get('nav-record-count').textContent = total.toLocaleString('id-ID');
  get('dashboard-empty').hidden = state.jobs.length > 0;
  get('dashboard-jobs').innerHTML = state.jobs.slice(0,10).map(job => `<tr><td><div class="source-cell"><span class="cell-icon">${icon('globe')}</span><div><div class="cell-title" data-user-content>${escapeHTML(hostname(job.url))}</div><span data-user-content class="cell-meta">${escapeHTML(job.id)}</span></div></div></td><td>${badge(job.status==='success'?'Berhasil':'Gagal',job.status==='success'?'green-soft':'red-soft')}</td><td class="number">${job.tables || 0}</td><td>${escapeHTML(timeLabel(job.time))}</td></tr>`).join('');
  get('dashboard-foot').textContent=`${state.jobs.length} proses pada sesi ini`;
  icons();
}
function renderHistory() {
  const text = get('history-search').value.toLowerCase(); const filter = get('history-status').value;
  const jobs = state.jobs.filter(job => job.url.toLowerCase().includes(text) && (filter === 'all' || job.status === filter));
  get('history-empty').hidden = jobs.length > 0;
  get('history-rows').innerHTML=jobs.map(job => `<tr><td><div class="cell-title" data-user-content>${escapeHTML(job.id)}</div><span data-user-content class="cell-meta" title="${escapeHTML(job.url)}">${escapeHTML(job.url)}</span></td><td>${badge(job.status==='success'?'Berhasil':'Gagal',job.status==='success'?'green-soft':'red-soft')}</td><td>${escapeHTML(timeLabel(job.time,true))}</td><td class="number">${job.duration}s</td><td class="number">${job.tables || 0}</td><td><button class="icon-button" data-job="${escapeHTML(job.id)}" aria-label="Detail proses ${escapeHTML(job.id)}">${icon('arrow-up-right')}</button></td></tr>`).join('');
  get('history-count').textContent=`${jobs.length} dari ${state.jobs.length} proses`;
  get('history-rows').querySelectorAll('[data-job]').forEach(button => button.addEventListener('click',() => showJob(state.jobs.find(job => job.id === button.dataset.job)))); icons();
}
function showDialog(title,body,actions,eyebrow='DETAIL DATA') {
  get('detail-title').textContent=title; get('detail-eyebrow').textContent=eyebrow;
  get('detail-body').innerHTML=body; get('detail-actions').replaceChildren();
  actions.forEach(action => { const button=document.createElement('button'); button.type='button'; button.className=`button ${action.style || 'secondary'}`; button.textContent=action.label; button.addEventListener('click',action.run); get('detail-actions').append(button); });
  get('detail-dialog').showModal(); icons();
}
function detailField(label,value,raw=false) { return `<div class="detail-field"><dt ${raw?'data-user-content':''}>${escapeHTML(label)}</dt><dd ${raw?'data-user-content':''}>${escapeHTML(value)}</dd></div>`; }
function showJob(job) {
  if (!job) return;
  showDialog(job.id,`<dl>${detailField('URL sumber',job.url)}${detailField('Waktu mulai',timeLabel(job.time,true))}${detailField('Status',job.status==='success'?'Berhasil':'Gagal')}${detailField('Durasi',`${job.duration} detik`)}${detailField('Hasil / pesan',job.message)}</dl><p class="field-hint">Riwayat menyimpan metadata proses. Hasil lengkap yang aktif hanya berasal dari scraping terbaru yang berhasil.</p>`,[{label:'Tutup',run:()=>get('detail-dialog').close()}],'RIWAYAT PROSES');
}
function filteredRows() { return getRows().filter(row => (reviewFilter==='all' || row.status===reviewFilter) && row.cells.some(cell => String(cell).toLowerCase().includes(query.toLowerCase()))); }
function renderDataWorkspace() {
  get(currentView==='verification'?'certificate-workspace':'verification-workspace').replaceChildren();
  const host=get(currentView==='verification'?'verification-workspace':'certificate-workspace');
  const tables=state.current?.tables || [];
  const hasTables=tables.length>0;
  if (tableIndex>=tables.length) tableIndex=0;
  host.innerHTML=`<div class="inline-notice">${icon('info')}<div><strong>${currentView==='verification'?'Pemeriksaan manual operator':'Data tabel sumber'}</strong><p>${currentView==='verification'?'Penandaan berlaku di sesi browser ini; sebagai catatan pemeriksaan data sumber.':'Kolom mengikuti tabel HTML sumber. Pemetaan ke skema khusus belum tersedia.'}</p></div></div>
  <div class="toolbar"><div class="search-field">${icon('search')}<input id="data-search" type="search" aria-label="Cari nilai pada tabel" placeholder="Cari pada tabel…" value="${escapeHTML(query)}" ${!hasTables?'disabled':''}></div><select id="table-select" aria-label="Pilih tabel sumber" ${!hasTables?'disabled':''}>${hasTables?tables.map((rows,i)=>`<option value="${i}" ${i===tableIndex?'selected':''}>Tabel ${i+1} · ${Math.max(0,rows.length-(firstRowHeader?1:0))} baris</option>`).join(''):'<option>Belum ada tabel</option>'}</select><select id="review-filter" aria-label="Filter pemeriksaan" ${!hasTables?'disabled':''}><option value="all">Semua pemeriksaan</option><option value="pending">Belum diperiksa</option><option value="reviewed">Sudah diperiksa</option><option value="correction">Perlu perbaikan</option></select><button id="export-data" class="button secondary toolbar-end" ${!hasTables?'disabled':''}>${icon('download')}Ekspor JSON</button><button id="export-excel" class="button primary" ${!hasTables?'disabled':''}>${icon('file-spreadsheet')}Ekspor Excel</button></div>
  <div class="data-caption"><span id="data-source-caption"></span><label><input id="header-toggle" type="checkbox" ${firstRowHeader?'checked':''} ${!hasTables?'disabled':''}>Baris pertama sebagai header</label></div>
  <div class="table-frame"><table class="data-table" id="data-table"><thead id="data-head"></thead><tbody id="data-rows"></tbody></table><div id="data-empty" class="empty-state" hidden></div></div><div class="table-foot"><span id="data-count"></span><div class="pagination"><button id="prev-page" class="icon-button" aria-label="Halaman sebelumnya">${icon('chevron-left')}</button><span id="page-counter"></span><button id="next-page" class="icon-button" aria-label="Halaman berikutnya">${icon('chevron-right')}</button></div></div>`;
  if (state.current) get('data-source-caption').append(safeLink(state.current.url,hostname(state.current.url)));
  else get('data-source-caption').textContent='Belum ada sumber data aktif';
  get('review-filter').value=reviewFilter;
  get('data-search').addEventListener('input',event=>{query=event.target.value;pageNumber=1;renderDataRows();});
  get('review-filter').addEventListener('change',event=>{reviewFilter=event.target.value;pageNumber=1;renderDataRows();});
  get('table-select').addEventListener('change',event=>{tableIndex=Number(event.target.value);pageNumber=1;renderDataRows();});
  get('header-toggle').addEventListener('change',event=>{firstRowHeader=event.target.checked;state.firstRowHeader=firstRowHeader;persist();pageNumber=1;renderDataWorkspace();renderDashboard();});
  get('prev-page').addEventListener('click',()=>{pageNumber--;renderDataRows();});
  get('next-page').addEventListener('click',()=>{pageNumber++;renderDataRows();});
  get('export-data').addEventListener('click',()=>downloadJSON({source:state.current.url,table:tableIndex+1,first_row_is_header:firstRowHeader,headers:tableHeaders(),review_scope:'manual_browser_session',rows:filteredRows().map(row=>({source_row:row.rawIndex+1,values:row.cells,review_status:row.status}))},'data-workspace.json'));
  get('export-excel').addEventListener('click', showExcelExport);
  renderDataRows();
}
function showExcelExport() {
  const headers = tableHeaders();
  const rows = filteredRows();
  if (!headers.length) { toast('Tabel belum memiliki kolom.'); return; }
  showDialog('Ekspor Excel', `<p>${rows.length} baris dari Tabel ${tableIndex+1} sesuai pencarian dan filter aktif, mencakup semua halaman.</p><p>Pilih kolom yang ingin diambil. Urutan kolom mengikuti tabel sumber.</p><div class="export-shortcuts"><button type="button" class="button secondary" id="select-export-all">Pilih semua</button><button type="button" class="button secondary" id="clear-export-all">Kosongkan pilihan</button></div><fieldset class="export-columns"><legend>Kolom yang diekspor</legend>${headers.map((label,i)=>`<label><input type="checkbox" name="export-column" value="${i}" checked><span><span data-user-content>${escapeHTML(label)}</span> <small>(kolom ${i+1})</small></span></label>`).join('')}</fieldset><p id="export-feedback" role="status" aria-live="polite"></p>`, [
    {label:'Batal', run:()=>get('detail-dialog').close()},
    {label:'Unduh Excel (.xlsx)', style:'primary', run:async()=>{
      const selected = [...get('detail-body').querySelectorAll('input[name="export-column"]:checked')].map(input=>Number(input.value));
      if (!selected.length) { get('export-feedback').textContent='Pilih minimal satu kolom.'; return; }
      const button = get('detail-actions').lastElementChild;
      button.disabled=true; get('export-feedback').textContent='Menyiapkan file Excel...';
      try {
        const response = await fetch('/export/excel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({headers:selected.map(i=>headers[i]), rows:rows.map(row=>selected.map(i=>String(row.cells[i] ?? '')))})});
        if (!response.ok) throw new Error('Ekspor gagal. Coba lagi atau kurangi jumlah data.');
        const url=URL.createObjectURL(await response.blob());
        const link=document.createElement('a'); link.href=url; link.download=`data-tabel-${tableIndex+1}.xlsx`; document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
        get('detail-dialog').close(); toast('File Excel berhasil diunduh.');
      } catch (error) { get('export-feedback').textContent=error instanceof TypeError?'Koneksi ke server gagal. Coba lagi.':error.message; }
      finally { button.disabled=false; }
    }}
  ], 'PILIH KOLOM');
  get('select-export-all').addEventListener('click',()=>get('detail-body').querySelectorAll('input[name="export-column"]').forEach(input=>input.checked=true));
  get('clear-export-all').addEventListener('click',()=>get('detail-body').querySelectorAll('input[name="export-column"]').forEach(input=>input.checked=false));
}
function tableHeaders() {
  const rows=state.current?.tables[tableIndex] || [];
  const width=rows.reduce((max,row)=>Math.max(max,row.length),0);
  return Array.from({length:width},(_,i)=>firstRowHeader?String(rows[0]?.[i] || `Kolom ${i+1}`):`Kolom ${i+1}`);
}
function renderDataRows() {
  const headers=tableHeaders(); const rows=filteredRows();
  const totalPages=Math.max(1,Math.ceil(rows.length/state.pageSize)); pageNumber=Math.max(1,Math.min(pageNumber,totalPages));
  const visible=rows.slice((pageNumber-1)*state.pageSize,pageNumber*state.pageSize);
  get('data-head').innerHTML=`<tr><th scope="col" class="row-index">Baris</th>${headers.map(h=>`<th scope="col" data-user-content>${escapeHTML(h)}</th>`).join('')}<th scope="col">Pemeriksaan</th><th scope="col"><span class="sr-only">Aksi</span></th></tr>`;
  get('data-rows').innerHTML=visible.map(row=>`<tr><td class="row-index">${row.rawIndex+1}</td>${headers.map((_,i)=>`<td data-user-content title="${escapeHTML(row.cells[i] || '')}">${escapeHTML(row.cells[i] || '—')}</td>`).join('')}<td>${badge(...reviewMeta[row.status])}</td><td class="action-cell"><button class="icon-button" data-record="${row.id}" aria-label="Periksa baris ${row.rawIndex+1}">${icon('arrow-up-right')}</button></td></tr>`).join('');
  get('data-empty').hidden=rows.length>0;
  if (!rows.length) get('data-empty').innerHTML=`<span class="empty-icon">${icon('table-2')}</span><h3>${state.current?.tables.length?'Tidak ada baris yang sesuai':'Belum ada tabel untuk diperiksa'}</h3><p>${state.current?.tables.length?'Ubah pencarian, filter pemeriksaan, atau pengaturan header tabel.':'Jalankan scraping pada halaman yang memuat tabel HTML. Hasil akan ditampilkan sesuai kolom sumber.'}</p><a class="button secondary" href="#scraping">Buka proses scraping${icon('arrow-right')}</a>`;
  get('data-count').textContent=rows.length?`${(pageNumber-1)*state.pageSize+1}–${Math.min(pageNumber*state.pageSize,rows.length)} dari ${rows.length} baris`:'0 baris';
  get('page-counter').textContent=`${pageNumber} / ${totalPages}`;
  get('prev-page').disabled=pageNumber<=1; get('next-page').disabled=pageNumber>=totalPages;
  get('export-data').disabled=rows.length===0;
  get('data-rows').querySelectorAll('[data-record]').forEach(button=>button.addEventListener('click',()=>showRecord(button.dataset.record)));
  icons();
}
function showRecord(id) {
  const row=getRows().find(item=>item.id===id); if (!row) return;
  const headers=tableHeaders();
  const mark=status=>{
    state.reviews[id]=status;persist();get('detail-dialog').close();renderDataRows();renderDashboard();toast(`Baris ${row.rawIndex+1}: ${reviewMeta[status][0].toLowerCase()}.`);
  };
  showDialog(`Baris ${row.rawIndex+1} · Tabel ${tableIndex+1}`,`<dl>${headers.map((header,i)=>detailField(header,row.cells[i] || '—',true)).join('')}${detailField('Status pemeriksaan',reviewMeta[row.status][0])}</dl><p class="field-hint">Bandingkan data dengan sumber. Status ini hanya catatan pemeriksaan manual di browser.</p>`,[
    {label:'Belum diperiksa',run:()=>mark('pending')},
    {label:'Perlu perbaikan',run:()=>mark('correction')},
    {label:'Sudah diperiksa',style:'primary',run:()=>mark('reviewed')}
  ]);
}
const resultTabs=[...document.querySelectorAll('[role=tab]')];
function selectTab(name) { resultTabs.forEach(tab=>{const active=tab.dataset.tab===name;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;get(`panel-${tab.dataset.tab}`).hidden=!active;}); }
resultTabs.forEach((tab,index)=>{
  tab.addEventListener('click',()=>selectTab(tab.dataset.tab));
  tab.addEventListener('keydown',event=>{
    let next;
    if(event.key==='ArrowRight') next=(index+1)%resultTabs.length;
    if(event.key==='ArrowLeft') next=(index+resultTabs.length-1)%resultTabs.length;
    if(event.key==='Home') next=0;if(event.key==='End') next=resultTabs.length-1;
    if(next!==undefined){event.preventDefault();selectTab(resultTabs[next].dataset.tab);resultTabs[next].focus();}
  });
});
function renderResult() {
  const data=state.current; get('scrape-output').hidden=!data; if(!data)return;
  get('result-title').textContent=data.title || 'Halaman tanpa judul';
  const source=safeLink(data.url,data.url);source.id='source-url';source.className='source-link';get('source-url').replaceWith(source);
  get('result-summary').textContent=`${data.text.length.toLocaleString('id-ID')} karakter teks · ${data.links.length} tautan · ${data.tables.length} tabel`;
  get('text-result').textContent=data.text || 'Tidak ada teks pada HTML halaman ini.';
  get('json-result').textContent=JSON.stringify(data,null,2);
  get('panel-links').replaceChildren();
  if(!data.links.length)get('panel-links').textContent='Tidak ada tautan HTTP/HTTPS pada halaman ini.';
  else{
    const list=document.createElement('ul');list.className='link-list';
    data.links.forEach(item=>{const li=document.createElement('li');const detail=document.createElement('small');detail.textContent=item.url;li.append(safeLink(item.url,item.text || 'Tautan tanpa teks'),detail);list.append(li);});get('panel-links').append(list);
  }
  const tables=get('panel-tables');tables.replaceChildren();
  if(!data.tables.length)tables.textContent='Tidak ditemukan tabel HTML. Halaman mungkin tidak memiliki tabel atau memuatnya lewat JavaScript.';
  data.tables.forEach((rows,index)=>{
    const title=document.createElement('h3');title.className='result-table-title';title.textContent=`Tabel ${index+1}`;
    const wrap=document.createElement('div');wrap.className='table-frame';
    const table=document.createElement('table');
    const caption=document.createElement('caption');caption.className='sr-only';caption.textContent=`Tabel sumber ${index+1}`;table.append(caption);
    const tbody=document.createElement('tbody');
    rows.forEach(cells=>{const tr=document.createElement('tr');cells.forEach(value=>{const td=document.createElement('td');td.textContent=value;td.dataset.userContent='';tr.append(td);});tbody.append(tr);});
    table.append(tbody);wrap.append(table);tables.append(title,wrap);
  });
}
get('scrape-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;
  const source=get('url').value.trim();const started=Date.now();const authMode=get('auth-mode').value;
  get('submit').disabled=true;get('submit').setAttribute('aria-busy','true');get('submit-label').textContent='Mengambil data…';
  get('submit').innerHTML=`${icon('loader-circle')}<span id="submit-label">Mengambil data…</span>`;icons();
  get('submit').querySelector('svg')?.classList.add('spinning');
  get('status').dataset.state='loading';get('status').textContent='Pengambilan berjalan. Hasil sebelumnya tetap tersedia sampai proses baru berhasil.';
  manualToken=authMode==='manual_login'?crypto.randomUUID().replaceAll('-',''):null;
  get('manual-login-controls').hidden=!manualToken;
  get('manual-login-feedback').textContent='';
  get('manual-login-continue').disabled=false;
  get('manual-login-cancel').disabled=false;
  if(manualToken)get('status').textContent='Menunggu login manual. Selesaikan login di jendela browser, lalu klik Sudah login di sini.';
  const job={id:`SCR-${String(started).slice(-8)}`,url:source,authMode,time:new Date(started).toISOString(),status:'error',tables:0,message:''};
  try {
    const response=await fetch('/scrape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:source,auth_mode:authMode,manual_token:manualToken})});
    let data;try{data=await response.json();}catch{throw new Error('Respons server tidak dapat dibaca. Periksa apakah aplikasi masih berjalan.');}
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Periksa format URL dan coba kembali.');
    if(!Array.isArray(data.tables)||!Array.isArray(data.links)||typeof data.text!=='string')throw new Error('Format hasil tidak sesuai. Periksa respons API.');
    state.current=data;state.reviews={};tableIndex=0;pageNumber=1;query='';
    job.status='success';job.tables=data.tables.length;job.message=`${data.links.length} tautan, ${data.tables.length} tabel, ${data.text.length} karakter teks.`;
    get('status').dataset.state='success';get('status').textContent=`Scraping selesai. ${data.tables.length} tabel dan ${data.links.length} tautan ditemukan.`;
    renderResult();selectTab('tables');
  }catch(error){
    job.message=error instanceof TypeError?'Koneksi ke aplikasi gagal. Pastikan server berjalan.':error.message;
    get('status').dataset.state='error';get('status').textContent=job.message;
  }finally{
    manualToken=null;get('manual-login-controls').hidden=true;
    job.duration=((Date.now()-started)/1000).toFixed(1);state.jobs.unshift(job);state.jobs=state.jobs.slice(0,20);persist();
    busy=false;get('submit').disabled=false;get('submit').removeAttribute('aria-busy');get('submit').innerHTML=`${icon('play')}<span id="submit-label">Mulai scraping</span>`;icons();
    renderDashboard();if(currentView==='history')renderHistory();if(['certificates','verification'].includes(currentView))renderDataWorkspace();
  }
});
async function sendManualAction(action) {
  if(!manualToken)return;
  const button=get(action==='continue'?'manual-login-continue':'manual-login-cancel');
  button.disabled=true;
  try{
    const response=await fetch(`/scrape/manual/${manualToken}/${action}`,{method:'POST'});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail || 'Sesi belum siap. Tunggu browser terbuka lalu coba lagi.');
    get('manual-login-feedback').textContent=action==='continue'?'Mengambil data memakai sesi login...':'Membatalkan login...';
  }catch(error){get('manual-login-feedback').textContent=error instanceof TypeError?'Koneksi server gagal. Coba lagi.':error.message;button.disabled=false;}
}
get('manual-login-continue').addEventListener('click',()=>sendManualAction('continue'));
get('manual-login-cancel').addEventListener('click',()=>sendManualAction('cancel'));
async function updateAuthMode() {
  if(get('auth-mode').value==='manual_login'){
    get('auth-info').hidden=false;
    get('auth-info').querySelector('strong').textContent='Login manual di jendela browser';
    get('auth-config-status').textContent='Isi SCRAPER_LOGIN_URL di .env dengan URL login situs. Username dan password diisi sendiri di browser, sehingga tidak wajib di .env.';
    get('auth-info').querySelectorAll('p')[1].textContent='Browser Chromium terbuka pada komputer tempat server berjalan. Selesaikan login dan CAPTCHA, kemudian klik Sudah login di aplikasi. Sesi ditutup setelah proses selesai. Login lintas domain belum didukung.';
    get('auth-hint').textContent='Untuk situs dengan CAPTCHA atau login bertahap pada domain yang sama. Batas login 5 menit.';
    get('extraction-method').textContent='Browser + login manual';
    return;
  }

  const generic=get('auth-mode').value==='site_login';
  if(generic){
    get('auth-info').hidden=false;
    get('auth-info').querySelector('strong').textContent='Login situs sesuai konfigurasi .env';
    get('auth-info').querySelectorAll('p')[1].textContent='Kredensial hanya dikirim ke domain SCRAPER_LOGIN_URL. Isi selector CSS jika formulir tidak terdeteksi. Login satu tahap; OTP/CAPTCHA dan SSO belum didukung.';
    get('auth-config-status').textContent='Isi SCRAPER_LOGIN_URL, SCRAPER_USERNAME, dan SCRAPER_PASSWORD di .env server. Gunakan akun yang sesuai dengan situs tujuan.';
    get('auth-hint').textContent='URL halaman data harus satu domain dengan URL login yang dikonfigurasi.';
    get('extraction-method').textContent='Browser + login situs';
    return;
  }
  get('auth-info').hidden=true;
  get('auth-hint').textContent='Mode publik mengambil HTML tanpa sesi login.';
  get('extraction-method').textContent='HTML statis';
}
get('auth-mode').addEventListener('change',updateAuthMode);
get('example').addEventListener('click',()=>{get('url').value='https://example.com';get('url').focus();});
get('download').addEventListener('click',()=>{if(state.current)downloadJSON(state.current,'hasil-scraping.json');});
get('history-search').addEventListener('input',renderHistory);get('history-status').addEventListener('change',renderHistory);
get('close-dialog').addEventListener('click',()=>get('detail-dialog').close());
get('detail-dialog').addEventListener('click',event=>{if(event.target===get('detail-dialog')){const r=get('detail-dialog').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)get('detail-dialog').close();}});
get('menu-toggle').addEventListener('click',()=>setMobileMenu(!get('sidebar').classList.contains('open')));
function closeMobileMenu() { setMobileMenu(false); get('menu-toggle').focus(); }
get('sidebar-overlay').addEventListener('click',closeMobileMenu);
get('sidebar-close').addEventListener('click',closeMobileMenu);
get('profile-button').addEventListener('click',()=>{get('profile-menu').hidden=!get('profile-menu').hidden;get('profile-button').setAttribute('aria-expanded',String(!get('profile-menu').hidden));});
document.addEventListener('click',event=>{if(!event.target.closest('.profile-wrap')){get('profile-menu').hidden=true;get('profile-button').setAttribute('aria-expanded','false');}});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){
    if(get('sidebar').classList.contains('open'))closeMobileMenu();
    if(!get('profile-menu').hidden)get('profile-button').focus();
    get('profile-menu').hidden=true;get('profile-button').setAttribute('aria-expanded','false');
  }
  if(event.key==='Tab' && get('sidebar').classList.contains('open')){
    const focusable=[...get('sidebar').querySelectorAll('a[href], button')];
    const first=focusable[0],last=focusable[focusable.length-1];
    if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
  }
});
get('settings-form').addEventListener('submit',event=>{event.preventDefault();state.operator=get('operator-name').value.trim()||'Operator lokal';state.pageSize=Number(get('page-size').value);persist();updateProfile();toast('Preferensi workspace disimpan untuk sesi browser ini.');});
get('clear-session').addEventListener('click',()=>{
  if(busy){toast('Tunggu proses scraping selesai sebelum menghapus sesi.');return;}
  showDialog('Hapus data sesi?', '<p>Hasil aktif, riwayat proses, dan status pemeriksaan akan dihapus dari browser ini. Unduh hasil terlebih dahulu jika masih diperlukan.</p>',[
    {label:'Batal',run:()=>get('detail-dialog').close()},
    {label:'Hapus data sesi',style:'danger',run:()=>{state.jobs=[];state.current=null;state.reviews={};tableIndex=0;persist();renderResult();renderDashboard();get('status').textContent='Siap mengambil data.';delete get('status').dataset.state;get('detail-dialog').close();toast('Data sesi telah dihapus.');}}
  ],'PENYIMPANAN WORKSPACE');
});
async function checkHealth(){
  try{const response=await fetch('/health');const data=await response.json();if(!response.ok||data.status!=='OK')throw new Error();get('server-health').innerHTML='<span class="dot green"></span>Server terhubung';}
  catch{get('server-health').innerHTML='<span class="dot red"></span>Server tidak terhubung';}
}
function updateDate(){get('today-label').textContent=new Intl.DateTimeFormat('id-ID',{timeZone:'Asia/Jakarta',day:'numeric',month:'long',year:'numeric'}).format(new Date());}
updateDate();
window.addEventListener('hashchange',()=>{navigate();get('main').focus({preventScroll:true});});
window.addEventListener('resize',()=>{if(window.innerWidth>760 || !get('sidebar').classList.contains('open'))setMobileMenu(false);});
updateProfile();renderResult();navigate();checkHealth();

document.querySelectorAll('.guide-jumps a').forEach(link=>link.addEventListener('click',event=>{
  event.preventDefault();
  document.querySelector(link.getAttribute('href')).scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
}));
document.querySelectorAll('[data-copy],[data-copy-target]').forEach(button=>button.addEventListener('click',async()=>{
  const value=button.dataset.copy || get(button.dataset.copyTarget).textContent;
  try{await navigator.clipboard.writeText(value);toast('Berhasil disalin.');}
  catch{toast('Tidak dapat menyalin otomatis. Pilih dan salin teks secara manual.');}
}));
