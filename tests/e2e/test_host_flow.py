"""E2E tests for the host flow."""
import re
import requests
from playwright.sync_api import Page, expect

TIMEOUT = 10000


def _goto(page, url):
    """Navigate and wait for network idle."""
    page.goto(url, wait_until="networkidle", timeout=15000)


def _create_session(page, base_url):
    """Helper: create session in browser, return code."""
    _goto(page, base_url)
    page.wait_for_selector("#host-name", state="visible", timeout=TIMEOUT)
    page.locator("#host-name").fill("Alice")
    page.locator("#create-session-form button[type=submit]").click()
    expect(page.locator("#session-page")).to_have_class(re.compile("active"), timeout=TIMEOUT)
    return page.locator("#display-code").text_content()


class TestHostCreatesSession:

    def test_landing_page_loads(self, page: Page, base_url):
        _goto(page, base_url)
        expect(page.locator("h1")).to_have_text("Check Splitter")
        expect(page.locator("#create-session-form")).to_be_visible()
        expect(page.locator("#join-session-form")).to_be_visible()

    def test_create_session_requires_name(self, page: Page, base_url):
        _goto(page, base_url)
        page.locator("#host-name").fill("")
        page.locator("#create-session-form button[type=submit]").click()
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"))

    def test_create_session_shows_code(self, page: Page, base_url):
        code = _create_session(page, base_url)
        assert len(code) == 6

    def test_session_page_has_upload_section(self, page: Page, base_url):
        _create_session(page, base_url)
        expect(page.locator("#upload-section")).to_be_visible()

    def test_session_code_buttons_visible(self, page: Page, base_url):
        _create_session(page, base_url)
        expect(page.locator("#copy-code-btn")).to_be_visible()
        expect(page.locator("#show-qr-btn")).to_be_visible()
        expect(page.locator("#end-session-btn")).to_be_visible()

    def test_participants_section_shows_host(self, page: Page, base_url):
        _create_session(page, base_url)
        expect(page.locator("#participants-count")).to_have_text("1", timeout=TIMEOUT)


def _host_with_items(page, base_url, api_url):
    """Create host session in browser, seed items via API (using token from localStorage)."""
    import requests
    
    code = _create_session(page, base_url)
    
    # Get host token from localStorage
    host_token = page.evaluate("""() => {
        const tokens = JSON.parse(localStorage.getItem('checkSplitter_hostToken') || '{}');
        const code = document.getElementById('display-code').textContent;
        return tokens[code.toUpperCase()] || null;
    }""")
    
    assert host_token, "Host token not found in localStorage"
    
    # Add items via API with the host token
    for item in [{"name": "Burger", "price": 12.99}, {"name": "Pizza", "price": 15.50}]:
        r = requests.post(
            f"{api_url}/sessions/{code}/items", 
            json=item,
            headers={"X-Host-Token": host_token}
        )
        assert r.status_code == 201, f"Failed to add item: {r.text}"
    
    # Wait a beat for DB writes to settle, then reload
    page.wait_for_timeout(500)
    page.reload(wait_until="networkidle", timeout=15000)
    expect(page.locator("#session-page")).to_have_class(re.compile("active"), timeout=15000)
    expect(page.locator("#items-section")).to_be_visible(timeout=TIMEOUT)
    return code


class TestHostWithItems:

    def test_items_visible(self, page: Page, base_url, api_url):
        _host_with_items(page, base_url, api_url)
        expect(page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(2, timeout=TIMEOUT)

    def test_add_item_manually(self, page: Page, base_url, api_url):
        _host_with_items(page, base_url, api_url)
        page.locator("#new-item-name").fill("Salad")
        page.locator("#new-item-price").fill("8.00")
        page.locator("#add-item-btn").click()
        expect(page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(3, timeout=TIMEOUT)

    def test_host_selects_item(self, page: Page, base_url, api_url):
        _host_with_items(page, base_url, api_url)
        page.locator("#items-list .item-row:not(.tax-item) .item-checkbox").first.click()
        expect(page.locator("#items-list .item-row.selected")).to_have_count(1, timeout=TIMEOUT)

    def test_host_total_updates(self, page: Page, base_url, api_url):
        _host_with_items(page, base_url, api_url)
        page.locator("#items-list .item-row:not(.tax-item) .item-checkbox").first.click()
        expect(page.locator("#items-list .item-row.selected")).to_have_count(1, timeout=TIMEOUT)
        page.wait_for_timeout(1000)
        assert "12.99" in page.locator("#host-items-total").text_content()

    def test_delete_item(self, page: Page, base_url, api_url):
        _host_with_items(page, base_url, api_url)
        expect(page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(2, timeout=TIMEOUT)
        page.locator(".item-delete").first.click()
        expect(page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(1, timeout=TIMEOUT)

    def test_change_tip(self, page: Page, base_url, api_url):
        _host_with_items(page, base_url, api_url)
        page.locator("#items-list .item-row:not(.tax-item) .item-checkbox").first.click()
        expect(page.locator("#items-list .item-row.selected")).to_have_count(1, timeout=TIMEOUT)
        page.locator(".host-tip-btn[data-tip='20']").click()
        page.wait_for_timeout(500)
        expect(page.locator("#host-tip-percent")).to_have_text("20")


class TestHostEndSession:

    def test_end_session_shows_confirmation(self, page: Page, base_url):
        _create_session(page, base_url)
        page.locator("#end-session-btn").click()
        expect(page.locator("#confirm-modal")).to_have_class(re.compile("active"), timeout=TIMEOUT)

    def test_end_session_returns_to_landing(self, page: Page, base_url):
        _create_session(page, base_url)
        page.locator("#end-session-btn").click()
        expect(page.locator("#confirm-modal")).to_have_class(re.compile("active"), timeout=TIMEOUT)
        page.locator("#confirm-ok").click()
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"), timeout=TIMEOUT)


class TestHostQRCode:

    def test_qr_modal_opens(self, page: Page, base_url):
        _create_session(page, base_url)
        page.locator("#show-qr-btn").click()
        expect(page.locator("#qr-modal")).to_have_class(re.compile("active"), timeout=TIMEOUT)

    def test_qr_modal_closes(self, page: Page, base_url):
        _create_session(page, base_url)
        page.locator("#show-qr-btn").click()
        expect(page.locator("#qr-modal")).to_have_class(re.compile("active"), timeout=TIMEOUT)
        page.locator("#qr-modal .close-btn").click()
        expect(page.locator("#qr-modal")).not_to_have_class(re.compile("active"), timeout=TIMEOUT)
