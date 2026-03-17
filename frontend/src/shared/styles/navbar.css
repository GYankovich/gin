.navbar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 60px;
    background: var(--navbar-bg, #ffffff);
    border-bottom: 1px solid var(--border-color, #e0e0e0);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 1.5rem;
    z-index: 1000;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.navbar-left {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.nav-items {
    display: flex;
    align-items: center;
    gap: 1.5rem;
}

.logo-minimal {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 1.5rem;
    font-weight: bold;
    cursor: pointer;
    transition: opacity 0.2s;
}

.logo-minimal:hover {
    opacity: 0.8;
}

.logo-g {
    color: var(--primary-color, #4a9eff);
}

.logo-in {
    color: var(--text-primary, #333);
}

.nav-link {
    background: none;
    border: none;
    color: var(--text-secondary, #666);
    font-size: 1rem;
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.2s;
    position: relative;
}

.nav-link:hover {
    background: var(--hover-bg, #f5f5f5);
    color: var(--text-primary, #333);
}

.nav-link-active {
    color: var(--primary-color, #4a9eff);
    font-weight: 500;
}

.nav-link-active::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 1rem;
    right: 1rem;
    height: 2px;
    background: var(--primary-color, #4a9eff);
    border-radius: 2px;
}

.navbar-right {
    position: relative;
}

.avatar-wrapper {
    cursor: pointer;
}

.avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--primary-color, #4a9eff);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    font-size: 1rem;
    transition: transform 0.2s, box-shadow 0.2s;
}

.avatar:hover {
    transform: scale(1.05);
    box-shadow: 0 4px 12px rgba(74, 158, 255, 0.3);
}

/* Дропдаун */
.dropdown {
    position: absolute;
    top: 50px;
    right: 0;
    width: 220px;
    background: var(--card-bg, #ffffff);
    border: 1px solid var(--border-color, #e0e0e0);
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    z-index: 1001;
    overflow: hidden;
    animation: dropdown-appear 0.2s ease-out;
}

@keyframes dropdown-appear {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.dropdown-item {
    padding: 0.75rem 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: var(--text-primary, #333);
    cursor: pointer;
    transition: background 0.2s;
}

.dropdown-item:hover {
    background: var(--hover-bg, #f5f5f5);
}

.dropdown-icon {
    font-size: 1.2rem;
    width: 24px;
    text-align: center;
}

.dropdown-divider {
    height: 1px;
    background: var(--border-color, #e0e0e0);
    margin: 0.5rem 0;
}

/* Мобильное меню */
.mobile-menu-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-primary, #333);
    padding: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
}

.mobile-menu-button:hover {
    background: var(--hover-bg, #f5f5f5);
}

.mobile-menu {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--card-bg, #ffffff);
    z-index: 2000;
    display: flex;
    flex-direction: column;
    animation: slide-in 0.3s ease-out;
}

@keyframes slide-in {
    from {
        transform: translateX(-100%);
    }
    to {
        transform: translateX(0);
    }
}

    .mobile-menu-header {
    height: 60px;
    padding: 0 1.5rem;
    border-bottom: 1px solid var(--border-color, #e0e0e0);
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.mobile-menu-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-primary, #333);
    padding: 0.5rem;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
}

.mobile-menu-close:hover {
    background: var(--hover-bg, #f5f5f5);
}

.mobile-menu-items {
    flex: 1;
    padding: 2rem 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.mobile-menu-item {
    background: none;
    border: none;
    padding: 1rem;
    font-size: 1.2rem;
    color: var(--text-primary, #333);
    cursor: pointer;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 1rem;
    transition: background 0.2s;
    width: 100%;
    text-align: left;
}

.mobile-menu-item:hover {
    background: var(--hover-bg, #f5f5f5);
}

.mobile-menu-item.active {
    color: var(--primary-color, #4a9eff);
    font-weight: 500;
}

.menu-item-icon {
    font-size: 1.5rem;
    width: 32px;
}

/* Тёмная тема */
[data-theme="dark"] {
    --navbar-bg: #1e1e1e;
    --border-color: #333;
    --text-primary: #fff;
    --text-secondary: #b0b0b0;
    --hover-bg: #2d2d2d;
    --card-bg: #2d2d2d;
    --primary-color: #4a9eff;
}

/* Светлая тема */
[data-theme="light"] {
    --navbar-bg: #ffffff;
    --border-color: #e0e0e0;
    --text-primary: #333;
    --text-secondary: #666;
    --hover-bg: #f5f5f5;
    --card-bg: #ffffff;
    --primary-color: #4a9eff;
}