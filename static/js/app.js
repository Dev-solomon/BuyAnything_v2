document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('.thumb').forEach(t=>t.addEventListener('click',()=>{document.querySelector('.gallery-main img').src=t.dataset.image;document.querySelectorAll('.thumb').forEach(x=>x.classList.remove('active'));t.classList.add('active')}));document.querySelectorAll('form button').forEach(b=>b.addEventListener('click',()=>{if(b.form&&b.form.checkValidity()){setTimeout(()=>{b.disabled=true;b.dataset.old=b.textContent;b.textContent='Working…'},30)}}))});

// Checkout quantity selector
(() => {
  const input = document.getElementById('quantity');
  if (!input) return;
  const unit = Number(window.BUYANYTHING_UNIT_PRICE || 0);
  const clamp = n => Math.max(1, Math.min(20, Number.isFinite(n) ? Math.trunc(n) : 1));
  const update = () => {
    const q = clamp(Number(input.value)); input.value = q;
    const amount = (unit * q).toFixed(2);
    const qtyLabel = document.getElementById('qty-label');
    const lineTotal = document.getElementById('line-total');
    const total = document.getElementById('checkout-total');
    if (qtyLabel) qtyLabel.textContent = `Qty ${q}`;
    if (lineTotal) lineTotal.textContent = `$${amount}`;
    if (total) total.textContent = `$${amount}`;
  };
  document.querySelectorAll('.qty-btn').forEach(btn => btn.addEventListener('click', () => { input.value = clamp(Number(input.value) + Number(btn.dataset.step)); update(); }));
  input.addEventListener('input', update); input.addEventListener('change', update); update();
})();

// V2 CJ variant-aware checkout totals/images.
document.addEventListener('DOMContentLoaded', () => {
  const variant = document.getElementById('variant_vid');
  const qty = document.getElementById('quantity');
  const total = document.getElementById('checkout-total');
  const line = document.getElementById('line-total');
  const label = document.getElementById('qty-label');
  const img = document.getElementById('checkout-image');
  if (!qty || !total) return;
  const refreshV2 = () => {
    let unit = Number(window.BUYANYTHING_UNIT_PRICE || 0);
    if (variant && variant.selectedOptions.length) {
      const opt = variant.selectedOptions[0];
      unit = Number(opt.dataset.price || unit);
      if (img && opt.dataset.image) img.src = opt.dataset.image;
    }
    let q = Math.max(1, Math.min(20, Number(qty.value || 1))); qty.value = q;
    const formatted = '$' + (unit*q).toFixed(2);
    total.textContent=formatted; if(line) line.textContent=formatted; if(label) label.textContent='Qty '+q;
  };
  variant?.addEventListener('change', refreshV2); qty.addEventListener('input', refreshV2);
  document.querySelectorAll('.qty-btn').forEach(b => b.addEventListener('click', () => setTimeout(refreshV2, 0)));
  refreshV2();
});

// Friendly multi-attribute CJ variant resolver. The browser displays human labels;
// only a server-imported CJ vid is submitted to Stripe/CJ fulfillment.
document.addEventListener('DOMContentLoaded', () => {
  const picker=document.getElementById('variant-picker'); if(!picker) return;
  const hidden=document.getElementById('variant_vid'), submit=document.getElementById('checkout-submit');
  const feedback=document.getElementById('variant-feedback'), label=document.getElementById('selected-variant-label');
  const img=document.getElementById('checkout-image'), qty=document.getElementById('quantity');
  let variants=[]; try{variants=JSON.parse(picker.dataset.variants||'[]')}catch(e){return}
  const selected={};
  const refreshTotals=(v)=>{const unit=Number((v&&v.retail_price)||window.BUYANYTHING_UNIT_PRICE||0); const q=Math.max(1,Math.min(20,Number(qty?.value||1))); const amount='$'+(unit*q).toFixed(2); const total=document.getElementById('checkout-total'),line=document.getElementById('line-total'); if(total)total.textContent=amount;if(line)line.textContent=amount;if(img&&v?.image)img.src=v.image;};
  const matches=(v)=>Object.entries(selected).every(([k,val])=>v.attributes&&String(v.attributes[k])===String(val));
  const resolve=()=>{
    const chosen=variants.filter(matches); const labels=[...picker.querySelectorAll('.option-group[data-option-label]')].map(x=>x.dataset.optionLabel);
    const complete=labels.length && labels.every(k=>selected[k]); const exact=complete&&chosen.length===1?chosen[0]:null;
    hidden.value=exact?.vid||''; submit.disabled=!exact;
    if(exact){feedback.textContent='Selected: '+exact.name;feedback.classList.add('ready');label.textContent=exact.name;refreshTotals(exact)}
    else{feedback.textContent=complete?'That combination is unavailable. Choose another option.':'Choose an available combination.';feedback.classList.remove('ready');label.textContent='Select your options below';refreshTotals(null)}
    picker.querySelectorAll('.option-chip:not(.direct-variant)').forEach(btn=>{const test={...selected,[btn.dataset.option]:btn.dataset.value};const possible=variants.some(v=>Object.entries(test).every(([k,val])=>v.attributes&&String(v.attributes[k])===String(val)));btn.classList.toggle('unavailable',!possible);btn.disabled=!possible});
  };
  picker.querySelectorAll('.option-chip:not(.direct-variant)').forEach(btn=>btn.addEventListener('click',()=>{selected[btn.dataset.option]=btn.dataset.value;picker.querySelectorAll(`.option-chip[data-option="${CSS.escape(btn.dataset.option)}"]`).forEach(x=>x.classList.remove('selected'));btn.classList.add('selected');resolve()}));
  picker.querySelectorAll('.direct-variant').forEach(btn=>btn.addEventListener('click',()=>{picker.querySelectorAll('.direct-variant').forEach(x=>x.classList.remove('selected'));btn.classList.add('selected');const v=variants.find(x=>String(x.vid)===String(btn.dataset.vid));hidden.value=v?.vid||'';submit.disabled=!v;if(v){feedback.textContent='Selected: '+v.name;feedback.classList.add('ready');label.textContent=v.name;refreshTotals(v)}}));
  qty?.addEventListener('input',()=>{const v=variants.find(x=>String(x.vid)===String(hidden.value));refreshTotals(v)});
  resolve();
});
