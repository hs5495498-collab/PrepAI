"""End-to-end Selenium coverage of the real PrepAI frontend against a real
(throwaway) backend instance - see conftest.py for how both servers and the
isolated test database are managed.

Tests in a class share one browser (module-scoped `driver` fixture) and run
in file order to mirror a real user's session: register -> use the app ->
log out. Edge cases that don't depend on that story get their own fresh
state within the flow instead of a separate browser, to keep the suite fast.

AI question generation / AI answer evaluation are never enabled here (see
conftest.py's backend_server fixture, which strips those env vars) - this
suite must never be able to trigger a paid OpenAI call.
"""
import uuid

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

TEST_PASSWORD = "SeleniumTest!2026"


def unique_email():
    return f"selenium.{uuid.uuid4().hex[:12]}@example.com"


def goto(driver, frontend_url, page):
    driver.get(f"{frontend_url}/{page}")


class TestAccountAndInterviewFlow:
    """One continuous story, in order, using one shared account."""

    email = unique_email()

    def test_01_home_page_loads(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "index.html")
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "body[data-page='dashboard']")))
        assert "PrepAI" in driver.title
        heading = driver.find_element(By.CSS_SELECTOR, ".page-heading")
        assert "Interview Journey" in heading.text

    def test_02_settings_shows_logged_out_state_initially(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "settings.html")
        logged_out = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        assert logged_out.is_displayed()
        logged_in = driver.find_element(By.ID, "account-loggedin")
        assert not logged_in.is_displayed()

    def test_03_backend_status_indicator_shows_connected(self, driver, wait):
        status_box = wait.until(
            EC.presence_of_element_located((By.ID, "backend-status"))
        )
        wait.until(lambda d: "is-ok" in status_box.get_attribute("class"))
        assert "Backend connected" in driver.find_element(By.ID, "backend-status-text").text

    def test_03b_topbar_login_link_visible_across_pages_when_logged_out(self, driver, wait, frontend_url):
        # Every page that loads js/api.js must show an explicit "Log In"
        # link in its topbar while logged out, pointed at the real login
        # form - not just settings.html, which has its own full account UI.
        for page in ("index.html", "achievements.html", "plan.html", "history.html", "analytics.html", "practice.html"):
            goto(driver, frontend_url, page)
            link = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-tools a")))
            wait.until(lambda d, link=link: link.text.strip() == "Log In")
            assert link.get_attribute("href").endswith("settings.html#account-section"), page
        goto(driver, frontend_url, "settings.html")

    def test_04_malformed_email_is_rejected(self, driver, wait):
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys("not-an-email")
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
        driver.find_element(By.ID, "authRegisterBtn").click()
        hint = wait.until(lambda d: d.find_element(By.ID, "authHint").text)
        assert hint.strip() != ""
        assert not driver.find_element(By.ID, "account-loggedin").is_displayed()

    def test_05_register_new_account(self, driver, wait):
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys(self.email)
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
        driver.find_element(By.ID, "authRegisterBtn").click()
        logged_in = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))
        assert logged_in.is_displayed()
        assert driver.find_element(By.ID, "accountEmail").text == self.email
        assert not driver.find_element(By.ID, "account-loggedout").is_displayed()

    def test_06_logged_in_state_persists_after_refresh(self, driver, wait):
        driver.refresh()
        logged_in = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))
        assert driver.find_element(By.ID, "accountEmail").text == self.email
        assert logged_in.is_displayed()

    def test_07_logout(self, driver, wait):
        driver.find_element(By.ID, "authLogoutBtn").click()
        logged_out = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        assert logged_out.is_displayed()
        assert not driver.find_element(By.ID, "account-loggedin").is_displayed()

    def test_08_duplicate_registration_rejected(self, driver, wait):
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys(self.email)
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
        driver.find_element(By.ID, "authRegisterBtn").click()
        hint = wait.until(lambda d: d.find_element(By.ID, "authHint").text)
        assert hint.strip() != ""
        assert not driver.find_element(By.ID, "account-loggedin").is_displayed()

    def test_09_login_with_wrong_password_rejected(self, driver, wait):
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys(self.email)
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys("totally-wrong-password")
        driver.find_element(By.ID, "authLoginBtn").click()
        hint = wait.until(lambda d: d.find_element(By.ID, "authHint").text)
        assert hint.strip() != ""
        assert not driver.find_element(By.ID, "account-loggedin").is_displayed()

    def test_10_login_with_correct_credentials(self, driver, wait):
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys(self.email)
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
        driver.find_element(By.ID, "authLoginBtn").click()
        logged_in = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))
        assert driver.find_element(By.ID, "accountEmail").text == self.email
        assert logged_in.is_displayed()

    def test_10b_topbar_shows_signed_in_email_across_pages_when_logged_in(self, driver, wait, frontend_url):
        for page in ("index.html", "achievements.html", "plan.html", "history.html", "analytics.html", "practice.html"):
            goto(driver, frontend_url, page)
            link = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-tools a")))
            wait.until(lambda d, link=link: link.text.strip() == self.email)
            assert link.get_attribute("href").endswith("settings.html#account-section"), page

    def test_11_start_interview(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("Software Engineer")
        Select(driver.find_element(By.ID, "setupCategory")).select_by_value("technical")
        Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("easy")
        Select(driver.find_element(By.ID, "setupCount")).select_by_value("5")
        driver.find_element(By.ID, "setupStart").click()
        session_panel = wait.until(EC.visibility_of_element_located((By.ID, "session")))
        assert session_panel.is_displayed()
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)

    def test_12_answer_and_navigate_all_questions(self, driver, wait):
        for i in range(1, 6):
            wait.until(lambda d, i=i: f"Question {i} of 5" in d.find_element(By.ID, "qcount").text)
            question_text = driver.find_element(By.ID, "question").text
            assert question_text.strip() != ""
            answer_box = driver.find_element(By.ID, "answer")
            answer_box.clear()
            # Question 1 deliberately includes raw HTML to verify the results
            # page escapes submitted answer text instead of rendering it.
            answer_text = "<b>test</b>" if i == 1 else f"Selenium automated answer for question {i}."
            answer_box.send_keys(answer_text)
            submit_btn = driver.find_element(By.ID, "submit")
            expected_label = "Finish Interview" if i == 5 else "Next Question"
            wait.until(lambda d, label=expected_label: d.find_element(By.ID, "submit").text == label)
            assert submit_btn.text == expected_label
            submit_btn.click()
            if i == 5:
                # "Finish Interview" triggers a native confirm() dialog.
                wait.until(EC.alert_is_present())
                driver.switch_to.alert.accept()

    def test_13_interview_completion_shows_results(self, driver, wait):
        wait.until(EC.url_contains("results.html"))
        result_box = wait.until(EC.visibility_of_element_located((By.ID, "result")))
        wait.until(lambda d: result_box.text.strip() != "")
        assert "(demo)" in result_box.text

        # Each question/answer pair lives in a collapsed <details> - expand
        # Q1 (whose answer was "<b>test</b>") to check it renders as literal
        # text, never as an actual bold element (no HTML injection from
        # the user's own input).
        first_qa = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result details.qa")))
        driver.execute_script("arguments[0].open = true;", first_qa)
        body_text = first_qa.find_element(By.CSS_SELECTOR, ".qa-body").text
        assert "<b>test</b>" in body_text
        bold_elements = first_qa.find_elements(By.TAG_NAME, "b")
        assert all(el.text != "test" for el in bold_elements)

    def test_14_history_shows_new_account_entry(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "history.html")
        account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-history-body")))
        wait.until(lambda d: account_body.text.strip() != "")
        assert "Software Engineer" in account_body.text or "Technical" in account_body.text
        local_section = driver.find_element(By.XPATH, "//h3[text()='Local Browser History (This Device Only)']")
        assert local_section.is_displayed()

    def test_15_analytics_and_recommendations_render(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "analytics.html")
        analytics_body = wait.until(EC.visibility_of_element_located((By.ID, "account-analytics-body")))
        wait.until(lambda d: analytics_body.text.strip() != "")
        reco_body = driver.find_element(By.ID, "recommendations-body")
        wait.until(lambda d: reco_body.text.strip() != "")

    def test_16_final_logout_returns_to_logged_out_state(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "settings.html")
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))
        driver.find_element(By.ID, "authLogoutBtn").click()
        logged_out = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        assert logged_out.is_displayed()


class TestLoggedOutStates:
    """Independent checks of logged-out-only behavior, own browser."""

    def test_history_logged_out_shows_local_section_only(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "history.html")
        wait.until(EC.visibility_of_element_located((By.ID, "account-history-body")))
        local_section = driver.find_element(By.XPATH, "//h3[text()='Local Browser History (This Device Only)']")
        assert local_section.is_displayed()

    def test_blank_answer_rejected_during_interview(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("QA Engineer")
        Select(driver.find_element(By.ID, "setupCategory")).select_by_value("hr")
        Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("easy")
        Select(driver.find_element(By.ID, "setupCount")).select_by_value("5")
        driver.find_element(By.ID, "setupStart").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        driver.find_element(By.ID, "answer").clear()
        driver.find_element(By.ID, "submit").click()
        hint = wait.until(lambda d: d.find_element(By.ID, "hint").text)
        assert hint.strip() != ""
        assert "Question 1 of 5" in driver.find_element(By.ID, "qcount").text

    def test_dashboard_offers_a_clear_login_link_when_logged_out(self, driver, wait, frontend_url):
        # Regression test for "login page is not showing": a logged-out
        # visitor must see an explicit way to log in right from the
        # dashboard's topbar, not just stumble onto Settings' Account
        # section by accident.
        goto(driver, frontend_url, "index.html")
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "body[data-page='dashboard']")))
        login_link = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-tools a")))
        wait.until(lambda d: login_link.text.strip() == "Log In")
        login_link.click()
        wait.until(EC.url_contains("settings.html#account-section"))
        logged_out = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        assert logged_out.is_displayed()

    def test_fifteen_question_interview_has_no_duplicate_questions(self, driver, wait, frontend_url):
        # Regression test for "interview questions repeat": a 15-question
        # interview must show 15 distinct questions, never 5 repeated 3x.
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("Software Engineer")
        Select(driver.find_element(By.ID, "setupCategory")).select_by_value("technical")
        Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("medium")
        Select(driver.find_element(By.ID, "setupCount")).select_by_value("15")
        driver.find_element(By.ID, "setupStart").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        wait.until(lambda d: "Question 1 of 15" in d.find_element(By.ID, "qcount").text)

        seen_questions = []
        for i in range(1, 16):
            wait.until(lambda d, i=i: f"Question {i} of 15" in d.find_element(By.ID, "qcount").text)
            seen_questions.append(driver.find_element(By.ID, "question").text)
            answer_box = driver.find_element(By.ID, "answer")
            answer_box.clear()
            answer_box.send_keys(f"Selenium answer for question {i}.")
            driver.find_element(By.ID, "submit").click()
            if i == 15:
                wait.until(EC.alert_is_present())
                driver.switch_to.alert.accept()

        assert len(seen_questions) == 15
        assert len(set(seen_questions)) == 15, "a 15-question interview repeated at least one question"
        wait.until(EC.url_contains("results.html"))


class TestOfflineDemoMode:
    """Stops the Selenium suite's own backend subprocess to verify the
    documented offline fallback, then restarts it so later tests/teardown
    still see a healthy server. Never touches a real/external backend
    process - see conftest.py's port-in-use guard."""

    def test_offline_demo_mode_completes_without_backend(self, driver, wait, frontend_url, backend_server):
        backend_server.stop()
        try:
            goto(driver, frontend_url, "practice.html")
            wait.until(EC.visibility_of_element_located((By.ID, "setup")))
            Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("Data Analyst")
            Select(driver.find_element(By.ID, "setupCategory")).select_by_value("behavioral")
            Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("easy")
            Select(driver.find_element(By.ID, "setupCount")).select_by_value("5")
            driver.find_element(By.ID, "setupStart").click()

            offline_btn = wait.until(EC.visibility_of_element_located((By.ID, "setupOfflineStart")))
            assert offline_btn.is_displayed()
            offline_btn.click()

            wait.until(EC.visibility_of_element_located((By.ID, "session")))
            for i in range(1, 6):
                wait.until(lambda d, i=i: f"Question {i} of 5" in d.find_element(By.ID, "qcount").text)
                answer_box = driver.find_element(By.ID, "answer")
                answer_box.clear()
                answer_box.send_keys(f"Offline demo answer {i}.")
                driver.find_element(By.ID, "submit").click()
                if i == 5:
                    wait.until(EC.alert_is_present())
                    driver.switch_to.alert.accept()

            wait.until(EC.url_contains("results.html"))
            result_box = wait.until(EC.visibility_of_element_located((By.ID, "result")))
            wait.until(lambda d: result_box.text.strip() != "")
            assert "(demo)" in result_box.text
        finally:
            backend_server.start()

    def test_offline_demo_fifteen_questions_has_no_duplicates(self, driver, wait, frontend_url, backend_server):
        # Regression test for "interview questions repeat", offline path:
        # the frontend's own pickOfflineQuestions() mirror of the backend
        # fix must also never repeat a question to pad out to 15.
        backend_server.stop()
        try:
            goto(driver, frontend_url, "practice.html")
            wait.until(EC.visibility_of_element_located((By.ID, "setup")))
            Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("Software Engineer")
            Select(driver.find_element(By.ID, "setupCategory")).select_by_value("technical")
            Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("medium")
            Select(driver.find_element(By.ID, "setupCount")).select_by_value("15")
            driver.find_element(By.ID, "setupStart").click()

            offline_btn = wait.until(EC.visibility_of_element_located((By.ID, "setupOfflineStart")))
            offline_btn.click()

            wait.until(EC.visibility_of_element_located((By.ID, "session")))
            wait.until(lambda d: "Question 1 of 15" in d.find_element(By.ID, "qcount").text)

            seen_questions = []
            for i in range(1, 16):
                wait.until(lambda d, i=i: f"Question {i} of 15" in d.find_element(By.ID, "qcount").text)
                seen_questions.append(driver.find_element(By.ID, "question").text)
                answer_box = driver.find_element(By.ID, "answer")
                answer_box.clear()
                answer_box.send_keys(f"Offline demo answer {i}.")
                driver.find_element(By.ID, "submit").click()
                if i == 15:
                    wait.until(EC.alert_is_present())
                    driver.switch_to.alert.accept()

            assert len(seen_questions) == 15
            assert len(set(seen_questions)) == 15, "offline 15-question demo repeated at least one question"
            wait.until(EC.url_contains("results.html"))
        finally:
            backend_server.start()
