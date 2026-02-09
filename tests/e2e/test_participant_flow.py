"""E2E tests for the participant flow."""
import re
import requests
from playwright.sync_api import Page, expect


class TestParticipantJoins:

    def test_join_with_valid_code(self, page: Page, base_url, create_session_via_api, add_items_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(code, [{"name": "Burger", "price": 12.99}], host_token=host_token)
        page.goto(base_url)
        page.locator("#session-code").fill(code)
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)

    def test_participant_sees_code(self, page: Page, base_url, create_session_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        page.goto(base_url)
        page.locator("#session-code").fill(code)
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)
        expect(page.locator("#participant-session-code")).to_have_text(code)

    def test_participant_sees_items(self, page: Page, base_url, create_session_via_api, add_items_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(code, [
            {"name": "Burger", "price": 12.99},
            {"name": "Pizza", "price": 15.50},
            {"name": "Fries", "price": 5.00},
        ], host_token=host_token)
        page.goto(base_url)
        page.locator("#session-code").fill(code)
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)
        expect(page.locator("#participant-items-list .item-row")).to_have_count(3, timeout=5000)

    def test_participant_name_displayed(self, page: Page, base_url, create_session_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        page.goto(base_url)
        page.locator("#session-code").fill(code)
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)
        expect(page.locator("#participant-name-display")).to_have_text("Bob")

    def test_join_case_insensitive(self, page: Page, base_url, create_session_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        page.goto(base_url)
        page.locator("#session-code").fill(code.lower())
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)


def _join(page, base_url, code, name="Bob"):
    """Helper to join a session as participant."""
    page.goto(base_url)
    page.locator("#session-code").fill(code)
    page.locator("#join-name").fill(name)
    page.locator("#join-session-form button[type=submit]").click()
    expect(page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)


class TestParticipantSelectsItems:

    def test_select_item(self, page: Page, base_url, create_session_via_api, add_items_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(code, [{"name": "Burger", "price": 12.99}], host_token=host_token)
        _join(page, base_url, code)
        expect(page.locator("#participant-items-list .item-row")).to_have_count(1, timeout=5000)
        page.locator("#participant-items-list .item-row").first.click()
        expect(page.locator("#participant-items-list .item-row.selected")).to_have_count(1, timeout=5000)

    def test_deselect_item(self, page: Page, base_url, create_session_via_api, add_items_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(code, [{"name": "Burger", "price": 12.99}], host_token=host_token)
        _join(page, base_url, code)
        expect(page.locator("#participant-items-list .item-row")).to_have_count(1, timeout=5000)
        page.locator("#participant-items-list .item-row").first.click()
        expect(page.locator("#participant-items-list .item-row.selected")).to_have_count(1, timeout=5000)
        page.locator("#participant-items-list .item-row").first.click()
        expect(page.locator("#participant-items-list .item-row.selected")).to_have_count(0, timeout=5000)

    def test_total_updates(self, page: Page, base_url, create_session_via_api, add_items_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(code, [{"name": "Burger", "price": 10.00}, {"name": "Pizza", "price": 20.00}], host_token=host_token)
        _join(page, base_url, code)
        expect(page.locator("#participant-items-list .item-row")).to_have_count(2, timeout=5000)
        page.locator("#participant-items-list .item-row").first.click()
        expect(page.locator("#participant-items-list .item-row.selected")).to_have_count(1, timeout=5000)
        page.wait_for_timeout(1000)
        assert "10.00" in page.locator("#your-items-total").text_content()

    def test_tip_buttons(self, page: Page, base_url, create_session_via_api, add_items_via_api):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(code, [{"name": "Burger", "price": 10.00}], host_token=host_token)
        _join(page, base_url, code)
        page.locator("#participant-page .tip-btn[data-tip='20']").click()
        expect(page.locator("#tip-percent-display")).to_have_text("20")


class TestParticipantLeave:

    def test_leave_button_visible(self, page: Page, base_url, create_session_via_api):
        session = create_session_via_api("Alice")
        _join(page, base_url, session["code"])
        expect(page.locator("#participant-leave-session-btn")).to_be_visible()

    def test_leave_returns_to_landing(self, page: Page, base_url, create_session_via_api):
        session = create_session_via_api("Alice")
        _join(page, base_url, session["code"])
        page.locator("#participant-leave-session-btn").click()
        expect(page.locator("#confirm-modal")).to_have_class(re.compile("active"), timeout=3000)
        page.locator("#confirm-ok").click()
        expect(page.locator("#landing-page")).to_have_class(re.compile("active"), timeout=5000)
