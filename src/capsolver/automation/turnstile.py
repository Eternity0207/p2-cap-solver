"""Turnstile sitekey extraction and token injection helpers."""

from __future__ import annotations

from capsolver.browser.page_adapter import PageAdapter

from capsolver.core.logging import get_logger

logger = get_logger(__name__)

EXTRACT_SITEKEY_JS = """() => {
    const el = document.querySelector('[data-sitekey]');
    if (el) return el.getAttribute('data-sitekey');
    const turnstile = document.querySelector('.cf-turnstile, [class*="turnstile"]');
    if (turnstile) {
        const sk = turnstile.getAttribute('data-sitekey');
        if (sk) return sk;
    }
    const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
    if (iframe && iframe.src) {
        const m = iframe.src.match(/0x4[A-Za-z0-9_-]+/);
        if (m) return m[0];
    }
    const html = document.documentElement.innerHTML;
    const m2 = html.match(/0x4[A-Za-z0-9_-]{10,}/);
    if (m2) return m2[0];
    return null;
}"""

INJECT_TOKEN_JS = """(token) => {
    const input = document.querySelector('input[name="cf-turnstile-response"]');
    if (!input) return { ok: false, reason: 'no_input' };
    input.value = token;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    const widget = document.querySelector('.cf-turnstile, [data-sitekey], [data-callback]');
    const cbName = widget?.getAttribute('data-callback');
    if (cbName && typeof window[cbName] === 'function') {
        try { window[cbName](token); return { ok: true, method: 'callback' }; } catch (e) {}
    }

    // Cloudflare managed challenge hooks
    for (const key of Object.keys(window)) {
        if (key.startsWith('cfCallback_') && typeof window[key] === 'function') {
            try { window[key](token); return { ok: true, method: key }; } catch (e) {}
        }
    }

    const form = input.closest('form') || document.querySelector('form#challenge-form, form');
    if (form) {
        try {
            if (typeof form.requestSubmit === 'function') form.requestSubmit();
            else form.submit();
            return { ok: true, method: 'form_submit' };
        } catch (e) {}
    }

    return { ok: true, method: 'input_only' };
}"""


async def extract_sitekey(page: PageAdapter) -> str | None:
    return await page.evaluate(EXTRACT_SITEKEY_JS)


async def inject_turnstile_token(page: PageAdapter, token: str) -> bool:
    result = await page.evaluate(INJECT_TOKEN_JS, token)
    logger.info("turnstile_token_injected", result=result)
    return bool(result and result.get("ok"))
