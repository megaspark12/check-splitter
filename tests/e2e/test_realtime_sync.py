"""E2E tests for real-time WebSocket sync between host and participant."""
import re
from playwright.sync_api import Browser, expect


class TestRealTimeSync:

    def test_host_sees_participant_join(self, browser: Browser, base_url):
        # Use separate contexts so localStorage doesn't leak between host and participant
        host_ctx = browser.new_context()
        part_ctx = browser.new_context()
        host_page = host_ctx.new_page()
        host_page.goto(base_url)
        host_page.locator("#host-name").fill("Alice")
        host_page.locator("#create-session-form button[type=submit]").click()
        expect(host_page.locator("#session-page")).to_have_class(re.compile("active"), timeout=5000)
        code = host_page.locator("#display-code").text_content()
        expect(host_page.locator("#participants-count")).to_have_text("1", timeout=5000)

        part_page = part_ctx.new_page()
        part_page.goto(base_url)
        part_page.locator("#session-code").fill(code)
        part_page.locator("#join-name").fill("Bob")
        part_page.locator("#join-session-form button[type=submit]").click()
        expect(part_page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)

        expect(host_page.locator("#participants-count")).to_have_text("2", timeout=10000)
        host_ctx.close()
        part_ctx.close()

    def test_participant_sees_new_item(self, browser: Browser, base_url, api_url):
        import requests
        
        host_ctx = browser.new_context()
        part_ctx = browser.new_context()

        host_page = host_ctx.new_page()
        host_page.goto(base_url)
        host_page.locator("#host-name").fill("Alice")
        host_page.locator("#create-session-form button[type=submit]").click()
        expect(host_page.locator("#session-page")).to_have_class(re.compile("active"), timeout=5000)
        code = host_page.locator("#display-code").text_content()

        # Get host token from localStorage
        host_token = host_page.evaluate("""() => {
            const tokens = JSON.parse(localStorage.getItem('checkSplitter_hostToken') || '{}');
            const code = document.getElementById('display-code').textContent;
            return tokens[code.toUpperCase()] || null;
        }""")
        assert host_token, "Host token not found in localStorage"

        # Add item via API with host token
        r = requests.post(
            f"{api_url}/sessions/{code}/items",
            json={"name": "Burger", "price": 12.99},
            headers={"X-Host-Token": host_token}
        )
        assert r.status_code == 201
        host_page.reload(wait_until="networkidle", timeout=15000)
        expect(host_page.locator("#items-section")).to_be_visible(timeout=5000)
        expect(host_page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(1, timeout=5000)

        # Participant joins in separate context
        part_page = part_ctx.new_page()
        part_page.goto(base_url)
        part_page.locator("#session-code").fill(code)
        part_page.locator("#join-name").fill("Bob")
        part_page.locator("#join-session-form button[type=submit]").click()
        expect(part_page.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)
        expect(part_page.locator("#participant-items-list .item-row")).to_have_count(1, timeout=5000)

        # Host adds another item via API
        r = requests.post(
            f"{api_url}/sessions/{code}/items",
            json={"name": "Steak", "price": 25.00},
            headers={"X-Host-Token": host_token}
        )
        assert r.status_code == 201

        # Participant should see 2 items via WebSocket sync
        expect(part_page.locator("#participant-items-list .item-row")).to_have_count(2, timeout=10000)
        host_ctx.close()
        part_ctx.close()

    def test_multiple_participants(self, browser: Browser, base_url, api_url):
        import requests
        
        host_ctx = browser.new_context()
        p1_ctx = browser.new_context()
        p2_ctx = browser.new_context()

        host_page = host_ctx.new_page()
        host_page.goto(base_url)
        host_page.locator("#host-name").fill("Alice")
        host_page.locator("#create-session-form button[type=submit]").click()
        expect(host_page.locator("#session-page")).to_have_class(re.compile("active"), timeout=5000)
        code = host_page.locator("#display-code").text_content()

        # Get host token from localStorage
        host_token = host_page.evaluate("""() => {
            const tokens = JSON.parse(localStorage.getItem('checkSplitter_hostToken') || '{}');
            const code = document.getElementById('display-code').textContent;
            return tokens[code.toUpperCase()] || null;
        }""")
        assert host_token, "Host token not found in localStorage"

        # Add items via API with host token
        for item in [{"name": "Burger", "price": 12.99}, {"name": "Pizza", "price": 15.50}]:
            r = requests.post(
                f"{api_url}/sessions/{code}/items",
                json=item,
                headers={"X-Host-Token": host_token}
            )
            assert r.status_code == 201
        
        host_page.reload(wait_until="networkidle", timeout=15000)
        expect(host_page.locator("#items-list .item-row:not(.tax-item)")).to_have_count(2, timeout=5000)

        p1 = p1_ctx.new_page()
        p1.goto(base_url)
        p1.locator("#session-code").fill(code)
        p1.locator("#join-name").fill("Bob")
        p1.locator("#join-session-form button[type=submit]").click()
        expect(p1.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)

        p2 = p2_ctx.new_page()
        p2.goto(base_url)
        p2.locator("#session-code").fill(code)
        p2.locator("#join-name").fill("Carol")
        p2.locator("#join-session-form button[type=submit]").click()
        expect(p2.locator("#participant-page")).to_have_class(re.compile("active"), timeout=5000)

        expect(p1.locator("#participant-items-list .item-row")).to_have_count(2, timeout=5000)
        expect(p2.locator("#participant-items-list .item-row")).to_have_count(2, timeout=5000)
        expect(host_page.locator("#participants-count")).to_have_text("3", timeout=10000)

        host_ctx.close()
        p1_ctx.close()
        p2_ctx.close()
