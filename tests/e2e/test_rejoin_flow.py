"""E2E tests for rejoin flow after page refresh."""

import re

from playwright.sync_api import Page, expect


class TestRejoinBanner:

    def test_auto_rejoin_host_after_refresh(self, page: Page, base_url):
        """Host auto-rejoins within 5-min window after refresh."""
        page.goto(base_url)
        page.locator("#host-name").fill("Alice")
        page.locator("#create-session-form button[type=submit]").click()
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        page.reload()
        # Auto-rejoin triggers within 5-min window
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=10000
        )

    def test_auto_rejoin_participant_after_refresh(
        self, page: Page, base_url, create_session_via_api
    ):
        """Participant auto-rejoins within 5-min window after refresh."""
        session = create_session_via_api("Alice")
        page.goto(base_url)
        page.locator("#session-code").fill(session["code"])
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        page.reload()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=10000
        )

    def test_host_code_preserved_after_rejoin(self, page: Page, base_url):
        """Host session code is preserved after auto-rejoin."""
        page.goto(base_url)
        page.locator("#host-name").fill("Alice")
        page.locator("#create-session-form button[type=submit]").click()
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        code = page.locator("#display-code").text_content()
        page.reload()
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=10000
        )
        expect(page.locator("#display-code")).to_have_text(code)

    def test_participant_name_preserved_after_rejoin(
        self, page: Page, base_url, create_session_via_api
    ):
        """Participant name is preserved after auto-rejoin."""
        session = create_session_via_api("Alice")
        page.goto(base_url)
        page.locator("#session-code").fill(session["code"])
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        page.reload()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=10000
        )
        expect(page.locator("#participant-name-display")).to_have_text("Bob")


class TestDataPersistence:

    def test_items_persist_host(self, page: Page, base_url, api_url):
        """Test that items persist after page refresh for host."""
        import requests

        page.goto(base_url)
        page.locator("#host-name").fill("Alice")
        page.locator("#create-session-form button[type=submit]").click()
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        code = page.locator("#display-code").text_content()

        # Get host token from localStorage
        host_token = page.evaluate("""() => {
            const tokens = JSON.parse(localStorage.getItem('checkSplitter_hostToken') || '{}');
            const code = document.getElementById('display-code').textContent;
            return tokens[code.toUpperCase()] || null;
        }""")
        assert host_token, "Host token not found in localStorage"

        # Add item via API with host token
        r = requests.post(
            f"{api_url}/sessions/{code}/items",
            json={"name": "Burger", "price": 12.99},
            headers={"X-Host-Token": host_token},
        )
        assert r.status_code == 201

        page.reload()
        expect(page.locator("#session-page")).to_have_class(
            re.compile("active"), timeout=10000
        )
        expect(page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(
            1, timeout=5000
        )

    def test_selections_persist_participant(
        self, page: Page, base_url, create_session_via_api, add_items_via_api
    ):
        session = create_session_via_api("Alice")
        code = session["code"]
        host_token = session["host_token"]
        add_items_via_api(
            code,
            [{"name": "Burger", "price": 12.99}, {"name": "Pizza", "price": 15.50}],
            host_token=host_token,
        )
        page.goto(base_url)
        page.locator("#session-code").fill(code)
        page.locator("#join-name").fill("Bob")
        page.locator("#join-session-form button[type=submit]").click()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=5000
        )
        expect(page.locator("#participant-items-list .item-row")).to_have_count(
            2, timeout=5000
        )
        page.locator("#participant-items-list .item-row").first.click()
        expect(
            page.locator("#participant-items-list .item-row.selected")
        ).to_have_count(1, timeout=5000)
        page.reload()
        expect(page.locator("#participant-page")).to_have_class(
            re.compile("active"), timeout=10000
        )
        expect(
            page.locator("#participant-items-list .item-row.selected")
        ).to_have_count(1, timeout=5000)
