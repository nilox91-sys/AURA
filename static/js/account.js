(() => {
    'use strict';
    window.AuraAccount={init(save=async()=>true){
        const node=id=>document.getElementById(id),connect=node('github-connect'),output=node('github-result');
        if(!connect)return;let timer,expires=0,disposed=false;
        async function api(path,data){const res=await fetch('/api/github/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await res.json();if(!res.ok)throw new Error(body.error||'GitHub non disponibile.');return body;}
        function stop(){clearTimeout(timer);node('github-code-box').hidden=true;connect.disabled=false;}
        async function status(){
            try {const data=await api('status');output.textContent=data.authenticated?'Collegato come @'+data.profile.login:data.configured?'Pronta per collegare il tuo account.':'Configura il Client ID della tua applicazione GitHub per iniziare.';
                connect.hidden=data.authenticated;
                for(const id of ['github-logout','github-disconnect'])if(node(id))node(id).hidden=!data.authenticated;
                if(node('github-require-login'))node('github-require-login').disabled=!data.authenticated;
            }catch(error){output.textContent=error.message;}
        }
        async function poll(){
            if(disposed)return;
            if(Date.now()>expires){stop();output.textContent='Codice scaduto. Puoi avviare un nuovo accesso.';return;}
            try {const data=await api('poll',{});
                if(data.state==='authenticated'){stop();if(document.body.dataset.page==='login'){location.href='/';return;}await status();return;}
                output.textContent='In attesa dell’autorizzazione su GitHub…';timer=setTimeout(poll,Math.max(5,data.interval||5)*1000);
            }catch(error){stop();output.textContent=error.message;}
        }
        connect.addEventListener('click',async()=>{
            connect.disabled=true;clearTimeout(timer);
            try{if(!await save()){stop();return;}const data=await api('start',{});node('github-code').textContent=data.user_code;node('github-code-box').hidden=false;output.textContent='Autorizza AURA usando il codice qui sotto.';expires=Date.now()+data.expires_in*1000;timer=setTimeout(poll,data.interval*1000);}
            catch(error){stop();output.textContent=error.message;}
        });
        node('github-logout')?.addEventListener('click',async()=>{try{stop();const data=await api('logout',{});location.href=data.redirect;}catch(error){output.textContent=error.message;}});
        node('github-disconnect')?.addEventListener('click',async()=>{try{await api('disconnect',{});stop();await status();}catch(error){output.textContent=error.message;}});
        window.addEventListener('pagehide',()=>{disposed=true;clearTimeout(timer);},{once:true});status();
    }};
    if(document.body.dataset.page==='login')window.AuraAccount.init();
})();
