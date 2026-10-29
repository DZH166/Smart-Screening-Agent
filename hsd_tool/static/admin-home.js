'use strict';
/**
 * Minimal shell for the Key-ledger overview page.
 *
 * The DeepSeek key management, the ledger copy view and the enable switch moved
 * to their own pages, so this page only refreshes itself and can sign out.
 */
(() => {
  const refresh = document.getElementById('admin-refresh');
  const logout = document.getElementById('admin-logout');
  const message = (text, error = false) => {
    const node = document.getElementById('admin-message');
    if (!node) return;
    node.textContent = text;
    node.classList.toggle('hidden', !text);
    node.classList.toggle('error', error);
  };
  refresh?.addEventListener('click', () => location.reload());
  logout?.addEventListener('click', async () => {
    logout.disabled = true;
    logout.textContent = '正在退出…';
    try {
      const response = await fetch('/admin/logout', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: {'X-HSD-Token': window.HSD_TOKEN || '', 'Content-Type': 'application/json'},
        body: '{}',
      });
      if (!response.ok) throw new Error('退出请求未完成，请重试。');
      location.replace('/admin/login');
    } catch (error) {
      message(error.message, true);
      logout.disabled = false;
      logout.textContent = '退出登录';
    }
  });
})();
