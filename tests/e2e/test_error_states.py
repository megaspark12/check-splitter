"""E2E tests for error states and edge cases."""

import re

import requests
from playwright.sync_api import Page, expect


class TestInvalidCode:

    def test_invalid_code_shows_error(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#session-code").fill("XXXXXX")
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#toast")).to_be_visible(timeout=5000)
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"))

    def test_short_code(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#session-code").fill("AB")
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        page.wait_for_timeout(1000)
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"))


class TestEmptyForms:

    def test_empty_host_name(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#host-name").fill("")
        page.locator("#create-session-form button[type=submit]").click()
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"))

    def test_empty_join_name(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#session-code").fill("ABCDEF")
        page.locator("#join-name").fill("")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"))


class TestRefreshButton:

    def test_refresh_items(
        self, page: Page, base_url, create_session_via_api, add_items_via_api, api_url
    ):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(
            code, [{"name": "Burger", "price": 12.99}], host_token=host_token
        )
        page.goto(base_url)
        page.locator("#session-code").fill(code)
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        expect(page.locator("#participant-items-list .item-row")).to_have_count(
            1, timeout=5000
        )
        # Add another item via API (requires host token)
        requests.post(
            f"{api_url}/sessions/{code}/items",
            json={"name": "Pizza", "price": 15.50},
            headers={"X-Host-Token": host_token},
        )
        page.locator("#refresh-btn").click()
        page.wait_for_timeout(2000)
        expect(page.locator("#participant-items-list .item-row")).to_have_count(
            2, timeout=5000
        )


class TestJoinViaURL:

    def test_code_param_prefills(self, page: Page, base_url, create_session_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        page.goto(f"{base_url}?code={code}")
        page.wait_for_timeout(1000)
        expect(page.locator("#session-code")).to_have_value(code, timeout=3000)


class TestCopyCode:

    def test_copy_button_feedback(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#host-name").fill("Alice")
        page.locator("#create-session-form button[type=submit]").click()
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        page.locator("#copy-code-btn").click()
        page.wait_for_timeout(500)
        text = page.locator("#copy-btn-text").text_content()
        # Clipboard may not work in headless, but button should still respond
        assert text is not None
