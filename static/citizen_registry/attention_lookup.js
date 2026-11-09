(function(){
  const root=document.getElementById('citizenLookupWidget');
  if(!root)return;
  const rut=document.getElementById('id_citizen_rut'), btn=document.getElementById('citizenLookupButton');
  const message=document.getElementById('citizenLookupMessage'), add=document.getElementById('citizenQuickAdd');
  const fields={requester:'name',requester_email:'email',requester_phone:'phone',address:'address'};
  const refresh=()=>{Object.keys(fields).forEach(name=>{let el=document.getElementById('id_'+name);if(el)el.readOnly=true})};
  refresh();
  function fill(data){Object.entries(fields).forEach(([field,key])=>{const el=document.getElementById('id_'+field);if(el)el.value=data[key]||''});rut.value=data.rut;refresh();add?.classList.add('d-none');message.className='small mt-2 text-success';message.textContent='Ciudadano encontrado. Datos autocompletados en solo lectura.'}
  async function lookup(){const value=rut.value.trim();if(!value){message.textContent='Ingresa un RUT.';return}
    message.textContent='Buscando…'; const response=await fetch(root.dataset.lookupUrl+'?rut='+encodeURIComponent(value),{credentials:'same-origin'});let data=await response.json().catch(()=>({}));
    if(response.ok && data.found){fill(data.citizen);return}
    refresh(); // Nunca habilitar la edición de datos personales en este formulario.
    message.className='small mt-2 '+(response.status===403?'text-danger':'text-muted');message.textContent=response.status===403?'No tienes permiso para consultar ciudadanos.':response.status===400?'Revisa el formato del RUT.':'No existe en el registro de ciudadanos.';
    if(response.ok)add?.classList.remove('d-none');
  }
  btn?.addEventListener('click',lookup);rut?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();lookup()}});
  rut?.addEventListener('input',()=>{refresh();add?.classList.add('d-none')});
  if(rut?.value){lookup()}
  const quick=document.getElementById('citizenQuickForm');if(!quick)return;
  const quickModal=document.getElementById('citizenQuickModal');
  const quickMember=quick.elements.is_neighborhood_member;
  function community(){let checked=quickMember?.checked;quick.querySelectorAll('[data-community-field]').forEach(el=>el.style.display=checked?'':'none');if(quick.elements.neighborhood_group)quick.elements.neighborhood_group.disabled=!checked;if(quick.elements.organization_role)quick.elements.organization_role.disabled=!checked}
  quickMember?.addEventListener('change',community);community();
  add?.addEventListener('click',()=>{
    if(quick.elements.rut)quick.elements.rut.value=rut.value;
    community();
    const mainModal=document.getElementById('attentionEntryModal');
    if(mainModal){
      mainModal.addEventListener('hidden.bs.modal',()=>bootstrap.Modal.getOrCreateInstance(quickModal).show(),{once:true});
      bootstrap.Modal.getOrCreateInstance(mainModal).hide();
    }else{bootstrap.Modal.getOrCreateInstance(quickModal).show()}
  });
  quickModal?.addEventListener('hidden.bs.modal',()=>{
    const parent=document.getElementById('attentionEntryModal');
    if(parent)bootstrap.Modal.getOrCreateInstance(parent).show();
  });
  quick.addEventListener('submit',async e=>{e.preventDefault();const resultBox=document.getElementById('citizenQuickErrors');resultBox.classList.add('d-none');
    const result=await fetch(quick.action,{method:'POST',headers:{'X-CSRFToken':quick.elements.csrfmiddlewaretoken.value,'X-Requested-With':'XMLHttpRequest'},body:new FormData(quick)});const data=await result.json().catch(()=>({}));
    if(result.ok&&data.ok){bootstrap.Modal.getOrCreateInstance(quickModal).hide();fill(data.citizen);return}
    resultBox.textContent=data.errors?Object.entries(data.errors).map(([k,vs])=>k+': '+vs.map(v=>v.message).join(', ')).join(' · '):'No fue posible registrar al ciudadano.';resultBox.classList.remove('d-none');
  });
})();
