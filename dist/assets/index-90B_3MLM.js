var f=Object.defineProperty;var p=(n,e,o)=>e in n?f(n,e,{enumerable:!0,configurable:!0,writable:!0,value:o}):n[e]=o;var a=(n,e,o)=>p(n,typeof e!="symbol"?e+"":e,o);(function(){const e=document.createElement("link").relList;if(e&&e.supports&&e.supports("modulepreload"))return;for(const t of document.querySelectorAll('link[rel="modulepreload"]'))r(t);new MutationObserver(t=>{for(const s of t)if(s.type==="childList")for(const c of s.addedNodes)c.tagName==="LINK"&&c.rel==="modulepreload"&&r(c)}).observe(document,{childList:!0,subtree:!0});function o(t){const s={};return t.integrity&&(s.integrity=t.integrity),t.referrerPolicy&&(s.referrerPolicy=t.referrerPolicy),t.crossOrigin==="use-credentials"?s.credentials="include":t.crossOrigin==="anonymous"?s.credentials="omit":s.credentials="same-origin",s}function r(t){if(t.ep)return;t.ep=!0;const s=o(t);fetch(t.href,s)}})();class m{constructor(){a(this,"state",{user:null,token:localStorage.getItem("token"),isLoading:!1});a(this,"listeners",[])}getState(){return{...this.state}}setUser(e){this.state.user=e,this.notify()}setToken(e){this.state.token=e,e?localStorage.setItem("token",e):localStorage.removeItem("token"),this.notify()}setLoading(e){this.state.isLoading=e,this.notify()}subscribe(e){return this.listeners.push(e),()=>{this.listeners=this.listeners.filter(o=>o!==e)}}notify(){this.listeners.forEach(e=>e(this.getState()))}}const i=new m;async function d(n,e={}){const{token:o,...r}=e,t={"Content-Type":"application/json",...r.headers};(o||i.getState().token)&&(t.Authorization=`Bearer ${o||i.getState().token}`);const s=await fetch(`/api${n}`,{...r,headers:t});if(!s.ok){s.status===401&&(i.setToken(null),i.setUser(null),window.location.href="/login");const c=await s.text();throw new Error(c||"API Error")}return s.json()}class y{constructor(){a(this,"tokenKey","auth_token")}async login(e){try{const o=await d("/auth/login",{method:"POST",body:JSON.stringify(e)});return this.setToken(o.access_token),o}catch(o){throw o}}async getCurrentUser(){return d("/auth/me",{token:this.getToken()})}async logout(){try{await d("/auth/logout",{method:"POST",token:this.getToken()})}finally{this.removeToken()}}setToken(e){localStorage.setItem(this.tokenKey,e)}getToken(){return localStorage.getItem(this.tokenKey)}removeToken(){localStorage.removeItem(this.tokenKey)}isAuthenticated(){return!!this.getToken()}}const h=new y;class w{constructor(){a(this,"routes",new Map);a(this,"currentPath",window.location.pathname);a(this,"wildcardHandler",null);window.addEventListener("popstate",()=>{this.handleRoute(window.location.pathname)})}register(e,o){e==="*"?this.wildcardHandler=o:this.routes.set(e,o)}navigate(e){window.history.pushState({},"",e),this.handleRoute(e)}handleRoute(e){const o=this.routes.get(e);o?(this.currentPath=e,o()):this.wildcardHandler?(this.currentPath=e,this.wildcardHandler()):console.warn(`No handler for path: ${e}`)}start(){this.handleRoute(this.currentPath)}}const l=new w;class v{constructor(e){a(this,"container");a(this,"error",null);a(this,"isLoading",!1);this.container=e}renderTemplate(){return`
      <div class="login-container">
        <div class="login-card">
          <div class="login-header">
            <div class="logo">
              <div class="logo-mark">G</div>
              <div class="logo-text">GAnal</div>
            </div>
            <h1 class="login-title">Вход в систему</h1>
            <p class="login-subtitle">Аналитика доходности и собственных средств</p>
          </div>

          <form id="login-form" class="login-form">
            <div class="form-group">
              <label class="form-label" for="login">Логин</label>
              <input 
                type="text" 
                id="login" 
                name="login" 
                class="form-input" 
                placeholder="Введите логин"
                required
                autocomplete="username"
              />
            </div>

            <div class="form-group">
              <label class="form-label" for="password">Пароль</label>
              <input 
                type="password" 
                id="password" 
                name="password" 
                class="form-input" 
                placeholder="Введите пароль"
                required
                autocomplete="current-password"
              />
            </div>

            ${this.error?`<div class="error-message">${this.error}</div>`:""}

            <button 
              type="submit" 
              class="login-button" 
              id="login-button"
              ${this.isLoading?"disabled":""}
            >
              ${this.isLoading?"Вход...":"Войти"}
            </button>
          </form>

          <div class="login-footer">
            <p class="hint">Демо: admin / admin123</p>
          </div>
        </div>
      </div>
    `}async handleSubmit(e){if(e.preventDefault(),this.isLoading)return;e.currentTarget;const o=document.getElementById("login"),r=document.getElementById("password");if(!o.value||!r.value){this.error="Заполните все поля",this.render();return}if(o.value.length<3){this.error="Логин должен быть минимум 3 символа",this.render();return}this.isLoading=!0,this.error=null,this.render();try{i.setLoading(!0);const t=await h.login({login:o.value,password:r.value}),s=await h.getCurrentUser();i.setUser(s),i.setToken(t.access_token),l.navigate("/analytics")}catch(t){console.error("Login error:",t),t instanceof Error?t.message.includes("401")||t.message.toLowerCase().includes("incorrect")?this.error="Неверный логин или пароль":t.message.includes("422")?this.error="Некорректные данные. Проверьте введенные значения":t.message.includes("500")?this.error="Ошибка сервера. Попробуйте позже":t.message.includes("Network Error")||t.message.includes("Failed to fetch")?this.error="Ошибка сети. Проверьте подключение к серверу":this.error=t.message:this.error="Произошла неизвестная ошибка"}finally{this.isLoading=!1,i.setLoading(!1);const t=o.value,s=r.value;this.render();const c=document.getElementById("login"),g=document.getElementById("password");c&&(c.value=t),g&&(g.value=s)}}attachEvents(){var o;const e=document.getElementById("login-form");if(e){const r=e.cloneNode(!0);(o=e.parentNode)==null||o.replaceChild(r,e),r.addEventListener("submit",t=>this.handleSubmit(t))}}render(){this.container.innerHTML=this.renderTemplate(),this.attachEvents()}}console.log("🚀 GAnal Frontend starting...");console.log("🔑 Токен:",i.getState().token?"есть":"нет");function b(n){n.innerHTML=`
    <div style="
      min-height: 100vh;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: Arial, sans-serif;
    ">
      <div style="
        background: white;
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        width: 100%;
        max-width: 800px;
        text-align: center;
      ">
        <h1 style="color: #333; margin-bottom: 20px;">📊 Аналитика</h1>
        <p style="color: #666; margin-bottom: 30px;">
          Добро пожаловать! Здесь будет отображаться ваша аналитика.
        </p>
        <div style="
          background: #f5f5f5;
          padding: 30px;
          border-radius: 10px;
          margin-bottom: 30px;
        ">
          <p style="color: #999;">Графики и метрики появятся здесь</p>
        </div>
        <button 
          onclick="localStorage.removeItem('token'); window.location.reload();"
          style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
          "
          onmouseover="this.style.transform='translateY(-2px)'"
          onmouseout="this.style.transform='none'"
        >
          Выйти
        </button>
      </div>
    </div>
  `}l.register("/login",()=>{console.log("👉 Рендеринг страницы логина");const n=document.getElementById("app");n&&(n.innerHTML="",new v(n).render())});l.register("/analytics",()=>{console.log("👉 Рендеринг страницы аналитики");const n=document.getElementById("app");n&&(n.innerHTML="",b(n))});l.register("*",()=>{console.log("👉 Любой другой путь"),!!i.getState().token?(console.log("🔑 Есть токен -> показываем аналитику"),l.navigate("/analytics")):(console.log("🔒 Нет токена -> показываем логин"),l.navigate("/login"))});l.start();const u=window.location.pathname;console.log(`📍 Текущий путь: ${u}`);u!=="/login"&&u!=="/analytics"&&(!!i.getState().token?l.navigate("/analytics"):l.navigate("/login"));
