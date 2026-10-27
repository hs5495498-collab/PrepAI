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
import time
import uuid

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

TEST_PASSWORD = "SeleniumTest!2026"


def unique_email():
    return f"selenium.{uuid.uuid4().hex[:12]}@example.com"


def goto(driver, frontend_url, page):
    driver.get(f"{frontend_url}/{page}")


def register(driver, wait, frontend_url, email):
    """Registers a brand-new account via settings.html and leaves the
    browser logged in. Shared by the Phase 2A recommendation tests below,
    each of which needs its own fresh account - logs out first if the
    shared module-scoped driver is still signed in from a prior test."""
    goto(driver, frontend_url, "settings.html")
    wait.until(lambda d: d.find_element(By.ID, "account-loggedout").is_displayed()
               or d.find_element(By.ID, "account-loggedin").is_displayed())
    if driver.find_element(By.ID, "account-loggedin").is_displayed():
        driver.find_element(By.ID, "authLogoutBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
    driver.find_element(By.ID, "authEmail").clear()
    driver.find_element(By.ID, "authEmail").send_keys(email)
    driver.find_element(By.ID, "authPassword").clear()
    driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
    driver.find_element(By.ID, "authRegisterBtn").click()
    wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))


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
        # This account's interview was created on the real backend (not
        # Offline Demo Mode), so results.html must route to the honest,
        # evaluation-aware view (renderBackendSession()) instead of ever
        # presenting the local word-count demo score as a verdict - no
        # evaluation was performed in this flow, so it must say so plainly
        # rather than show a misleading Passed/Unsuccessful/score.
        wait.until(EC.url_contains("results.html"))
        result_box = wait.until(EC.visibility_of_element_located((By.ID, "result")))
        wait.until(lambda d: result_box.text.strip() != "")
        assert "Not evaluated yet" in result_box.text
        assert "Unsuccessful" not in result_box.text
        assert "Passed" not in result_box.text

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

    def test_13b_dashboard_shows_honest_account_overview(self, driver, wait, frontend_url):
        # Regression test for the Dashboard blending live and sample data:
        # the account just completed one interview in this flow (test_11-13)
        # with no AI evaluation performed, so "Your Account Overview" must
        # say so honestly - never a fabricated score, verdict, or trend -
        # while the separate, clearly-labeled sample section is unaffected.
        goto(driver, frontend_url, "index.html")
        overview = wait.until(EC.visibility_of_element_located((By.ID, "account-overview-body")))
        wait.until(lambda d: "Loading" not in overview.text)
        assert "Not evaluated" in overview.text
        assert "Needs 2+ evaluated answers" in overview.text
        assert "Unsuccessful" not in overview.text

        sample_heading = driver.find_element(By.XPATH, "//h3[text()='Sample Dashboard Preview']")
        assert sample_heading.is_displayed()
        metrics = driver.find_element(By.ID, "metrics")
        assert metrics.is_displayed() and metrics.text.strip() != ""

    def test_14_history_shows_new_account_entry(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "history.html")
        account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-history-body")))
        wait.until(lambda d: account_body.text.strip() != "")
        assert "Software Engineer" in account_body.text or "Technical" in account_body.text
        local_section = driver.find_element(By.XPATH, "//h3[text()='Local Browser History (This Device Only)']")
        assert local_section.is_displayed()

        # Regression test: the Local Browser History table's Score column
        # must never show a raw demoScore() number in the same row where
        # the Result column honestly says "Not evaluated" - the interview
        # completed in test_11-13 has no real evaluation (AI is disabled
        # in this suite), so its row's Score and Result cells must agree.
        first_row = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#rows tr")))
        score_cell = first_row.find_element(By.CSS_SELECTOR, "[data-label='Score']")
        result_cell = first_row.find_element(By.CSS_SELECTOR, "[data-label='Result']")
        assert score_cell.text.strip() == "Not evaluated"
        assert "Not evaluated" in result_cell.text

    def test_15_analytics_and_recommendations_render(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "analytics.html")
        analytics_body = wait.until(EC.visibility_of_element_located((By.ID, "account-analytics-body")))
        wait.until(lambda d: analytics_body.text.strip() != "")
        reco_body = driver.find_element(By.ID, "recommendations-body")
        wait.until(lambda d: reco_body.text.strip() != "")

        # This account has one completed, unevaluated interview at this
        # point in the flow (test_11-13) - the real account section must say
        # so honestly, never a fabricated score or Passed/Unsuccessful
        # verdict, while the separate sample section is unaffected.
        assert "none of your answers have been evaluated yet" in analytics_body.text
        assert "Unsuccessful" not in analytics_body.text
        sample_heading = driver.find_element(By.XPATH, "//h3[text()='Sample Dashboard Preview']")
        assert sample_heading.is_displayed()
        assert driver.find_element(By.ID, "metrics").is_displayed()

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
        # Wait for the question content itself to be drawn, not just the
        # container becoming visible - matches the same pattern already
        # used by test_11_start_interview and the 15-question tests below.
        # Without this, reading #qcount immediately after the container
        # becomes visible is occasionally flaky (observed ~1/3 runs).
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)
        driver.find_element(By.ID, "answer").clear()
        driver.find_element(By.ID, "submit").click()
        hint = wait.until(lambda d: d.find_element(By.ID, "hint").text)
        assert hint.strip() != ""
        assert "Question 1 of 5" in driver.find_element(By.ID, "qcount").text

    def test_previous_question_answer_is_preserved_and_locked_after_submit(self, driver, wait, frontend_url):
        # Covers "navigate between questions without losing answers" and
        # "prevent unintended duplicate answer submission": going back to
        # an already-submitted question must show the same answer text,
        # with the answer box locked (matching the backend's 409 on a
        # duplicate answer - see backend/main.py's AlreadyCompleted/
        # DuplicateAnswer handling).
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("QA Engineer")
        Select(driver.find_element(By.ID, "setupCategory")).select_by_value("behavioral")
        Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("easy")
        Select(driver.find_element(By.ID, "setupCount")).select_by_value("5")
        driver.find_element(By.ID, "setupStart").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)

        answer_text = "My answer to question one."
        driver.find_element(By.ID, "answer").send_keys(answer_text)
        driver.find_element(By.ID, "submit").click()
        wait.until(lambda d: "Question 2 of 5" in d.find_element(By.ID, "qcount").text)

        driver.find_element(By.ID, "prev").click()
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)
        answer_box = driver.find_element(By.ID, "answer")
        assert answer_box.get_attribute("value") == answer_text
        assert answer_box.get_attribute("disabled") is not None
        hint_text = driver.find_element(By.ID, "hint").text
        assert "already" in hint_text.lower()

    def test_dashboard_offers_a_clear_login_link_when_logged_out(self, driver, wait, frontend_url):
        # Regression test for "login page is not showing": a logged-out
        # visitor must see an explicit way to log in right from the
        # dashboard's topbar, not just stumble onto Settings' Account
        # section by accident.
        goto(driver, frontend_url, "index.html")
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "body[data-page='dashboard']")))
        # The real "Your Account Overview" section must never show sample
        # data or a fabricated score to a logged-out visitor - it must
        # plainly ask them to sign in instead.
        overview = wait.until(EC.visibility_of_element_located((By.ID, "account-overview-body")))
        wait.until(lambda d: "Loading" not in overview.text)
        assert "Sign in" in overview.text
        login_link = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-tools a")))
        wait.until(lambda d: login_link.text.strip() == "Log In")
        login_link.click()
        wait.until(EC.url_contains("settings.html#account-section"))
        logged_out = wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        assert logged_out.is_displayed()

    def test_analytics_shows_honest_sign_in_prompt_and_separate_sample_data_when_logged_out(self, driver, wait, frontend_url):
        # Regression test for analytics.html blending sample and account
        # data: a logged-out visitor's real "Your Account Analytics" section
        # must plainly ask them to sign in, while the separate, clearly-
        # labeled sample section still renders its own illustrative data.
        goto(driver, frontend_url, "analytics.html")
        account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-analytics-body")))
        wait.until(lambda d: "Loading" not in account_body.text)
        assert "Sign in" in account_body.text

        sample_heading = driver.find_element(By.XPATH, "//h3[text()='Sample Dashboard Preview']")
        assert sample_heading.is_displayed()
        metrics = driver.find_element(By.ID, "metrics")
        assert metrics.is_displayed() and metrics.text.strip() != ""
        assert "Not evaluated" not in metrics.text  # the sample tiles are fixed numbers, never this wording

    def test_achievements_shows_honest_sign_in_prompt_and_separate_sample_data_when_logged_out(self, driver, wait, frontend_url):
        # Regression test for achievements.html blending sample and account
        # milestones: a logged-out visitor's real "Your Account Achievements"
        # section must plainly ask them to sign in, while the separate,
        # clearly-labeled sample section still renders its own illustrative
        # milestones (unaffected by any real account activity).
        goto(driver, frontend_url, "achievements.html")
        account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-achievements-body")))
        wait.until(lambda d: "Loading" not in account_body.text)
        assert "Sign in" in account_body.text

        sample_heading = driver.find_element(By.XPATH, "//h3[text()='Sample Dashboard Preview']")
        assert sample_heading.is_displayed()
        featured = driver.find_element(By.ID, "featured")
        assert featured.is_displayed() and featured.text.strip() != ""

    def test_achievement_milestone_thresholds_are_correct(self, driver, wait, frontend_url):
        # Score-based achievements must require genuine evaluation data, and
        # every threshold must match data.js's documented definitions. AI
        # evaluation can never be exercised in this suite (no paid calls),
        # so this verifies the real, shipped data.js threshold logic
        # directly in a real browser's JS engine with synthetic data,
        # instead of needing a live AI-evaluated interview to prove it.
        goto(driver, frontend_url, "achievements.html")
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "body[data-page='achievements']")))

        result = driver.execute_script("""
            var d1 = new Date('2026-01-01'), d2 = new Date('2026-01-02');
            var byId = {};
            window.PREP.achievements.forEach(function (a) { byId[a.id] = a; });
            return {
                e80_locked_at_79: byId.e80.test([{date: d1, score: 79}]),
                e80_unlocked_at_80: !!byId.e80.test([{date: d1, score: 80}]),
                pass_locked_empty: byId.pass.test([]),
                first_locked_empty: byId.first.test([]),
                first_unlocked_one: !!byId.first.test([{date: d1}]),
                five_locked_at_four: byId.five.test([{date: d1}, {date: d1}, {date: d1}, {date: d1}]),
                five_unlocked_at_five: !!byId.five.test([{date: d1}, {date: d1}, {date: d1}, {date: d1}, {date: d1}]),
                plus20_empty_does_not_throw: byId.plus20.test([]),
                plus20_locked_at_19: byId.plus20.test([{date: d1, score: 50}, {date: d2, score: 69}]),
                plus20_unlocked_at_20: !!byId.plus20.test([{date: d1, score: 50}, {date: d2, score: 70}]),
                e90_progress_empty_does_not_throw: byId.e90.progress([])
            };
        """)
        assert result["e80_locked_at_79"] is None
        assert result["e80_unlocked_at_80"] is True
        assert result["pass_locked_empty"] is None
        assert result["first_locked_empty"] is None
        assert result["first_unlocked_one"] is True
        assert result["five_locked_at_four"] is None
        assert result["five_unlocked_at_five"] is True
        assert result["plus20_empty_does_not_throw"] is None
        assert result["plus20_locked_at_19"] is None
        assert result["plus20_unlocked_at_20"] is True
        assert result["e90_progress_empty_does_not_throw"] == ""

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

    def test_question_stays_visible_several_seconds_after_starting_and_after_each_answer(self, driver, wait, frontend_url):
        # Regression test for a reported "question appears and then
        # disappears" bug. Root-caused to a local-dev-environment issue, not
        # application code (see docs/BROWSER_TEST_CHECKLIST.md and the
        # session report): some static-file dev servers (e.g. a live-reload
        # tool whose serving root is mistakenly the whole repo instead of
        # just prepai/) watch backend/data/prepai.db for changes and push a
        # full-page reload every time the backend writes to it - which is
        # every single interview-related API call. This suite's own static
        # server (see conftest.py) is correctly scoped to serve only
        # `prepai/` with no live-reload, so it cannot reproduce that
        # external failure mode - this test instead locks in that the
        # *application* keeps the question visible and the session state
        # intact well after each database-writing request, which is the
        # guarantee the application itself is actually responsible for.
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("Software Engineer")
        Select(driver.find_element(By.ID, "setupCategory")).select_by_value("technical")
        Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("easy")
        Select(driver.find_element(By.ID, "setupCount")).select_by_value("5")
        driver.find_element(By.ID, "setupStart").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)

        for i in range(1, 6):
            wait.until(lambda d, i=i: f"Question {i} of 5" in d.find_element(By.ID, "qcount").text)
            question_text_before = driver.find_element(By.ID, "question").text
            assert question_text_before.strip() != ""
            # The actual bug report: wait several real seconds (well past
            # any single request/response round trip) and confirm the
            # question and session are still there, unchanged, not reset
            # back to the setup screen.
            time.sleep(3)
            assert driver.find_element(By.ID, "session").is_displayed()
            assert not driver.find_element(By.ID, "setup").is_displayed()
            assert driver.find_element(By.ID, "question").text == question_text_before
            answer_box = driver.find_element(By.ID, "answer")
            answer_box.clear()
            answer_box.send_keys(f"Answer that must survive a few seconds, question {i}.")
            driver.find_element(By.ID, "submit").click()
            if i == 5:
                wait.until(EC.alert_is_present())
                driver.switch_to.alert.accept()
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
            # The failed createInterview() request must show a real error
            # message and keep the setup form visible - never leave a
            # blank/stuck interview screen behind.
            assert driver.find_element(By.ID, "setupHint").text.strip() != ""
            assert not driver.find_element(By.ID, "session").is_displayed()
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
            # A genuinely offline attempt has no backend session at all, so
            # it can never be AI-evaluated - never a demo-score pass/fail
            # verdict, just an honestly-labeled simulated number.
            assert "(simulated)" in result_box.text
            assert "Offline Demo Mode" in result_box.text
            assert "Unsuccessful" not in result_box.text
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


class TestCrossAccountIsolation:
    """Real-browser verification that one account's interview is never
    readable by a different account. backend/tests/test_history_api.py and
    test_auth.py already cover this at the API level with direct requests;
    this class exercises the same guarantee through the actual UI with two
    real accounts, real cookies, and a real session_id taken from the
    account-history page's own link - not a hand-constructed URL."""

    email_a = unique_email()
    email_b = unique_email()
    shared_session_url = {}

    def test_account_a_creates_an_interview_and_captures_its_link(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "settings.html")
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys(self.email_a)
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
        driver.find_element(By.ID, "authRegisterBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))

        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        Select(driver.find_element(By.ID, "setupRole")).select_by_visible_text("QA Engineer")
        Select(driver.find_element(By.ID, "setupCategory")).select_by_value("technical")
        Select(driver.find_element(By.ID, "setupDifficulty")).select_by_value("easy")
        Select(driver.find_element(By.ID, "setupCount")).select_by_value("5")
        driver.find_element(By.ID, "setupStart").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        for i in range(1, 6):
            wait.until(lambda d, i=i: f"Question {i} of 5" in d.find_element(By.ID, "qcount").text)
            answer_box = driver.find_element(By.ID, "answer")
            answer_box.clear()
            answer_box.send_keys("Account A's private answer - must never be visible to account B.")
            driver.find_element(By.ID, "submit").click()
            if i == 5:
                wait.until(EC.alert_is_present())
                driver.switch_to.alert.accept()
        wait.until(EC.url_contains("results.html"))

        goto(driver, frontend_url, "history.html")
        row_link = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#account-history-body a.view-link")))
        href = row_link.get_attribute("href")
        assert "results.html?session=" in href
        TestCrossAccountIsolation.shared_session_url["url"] = href

        # Account A just completed its first (unevaluated) real interview -
        # "First interview completed" (a count-based milestone) must unlock
        # on the real account section, while no score-based milestone does.
        goto(driver, frontend_url, "achievements.html")
        achievements_body = wait.until(EC.visibility_of_element_located((By.ID, "account-achievements-body")))
        wait.until(lambda d: "Loading" not in achievements_body.text)
        assert "First interview completed" in achievements_body.text
        assert "Scored 80 or higher" in achievements_body.text  # still listed, just locked
        locked_rows = driver.find_elements(By.CSS_SELECTOR, "#account-achievements-body .ach-row.locked .row-title")
        assert any(r.text == "Scored 80 or higher" for r in locked_rows)

        goto(driver, frontend_url, "settings.html")
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))
        driver.find_element(By.ID, "authLogoutBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))

    def test_account_b_cannot_view_account_as_interview(self, driver, wait, frontend_url):
        assert "url" in TestCrossAccountIsolation.shared_session_url, "account A's session link was not captured"

        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))
        driver.find_element(By.ID, "authEmail").clear()
        driver.find_element(By.ID, "authEmail").send_keys(self.email_b)
        driver.find_element(By.ID, "authPassword").clear()
        driver.find_element(By.ID, "authPassword").send_keys(TEST_PASSWORD)
        driver.find_element(By.ID, "authRegisterBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))

        driver.get(TestCrossAccountIsolation.shared_session_url["url"])
        result_box = wait.until(EC.visibility_of_element_located((By.ID, "result")))
        wait.until(lambda d: result_box.text.strip() not in ("", "Loading your interview…"))
        assert "could not be found" in result_box.text.lower()
        assert "Account A's private answer" not in result_box.text
        assert "QA Engineer" not in result_box.text

        goto(driver, frontend_url, "history.html")
        account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-history-body")))
        wait.until(lambda d: account_body.text.strip() != "")
        assert "QA Engineer" not in account_body.text

        # Account B has zero interviews of its own - account A's "First
        # interview completed" unlock must never leak into B's achievements.
        goto(driver, frontend_url, "achievements.html")
        achievements_body = wait.until(EC.visibility_of_element_located((By.ID, "account-achievements-body")))
        wait.until(lambda d: "Loading" not in achievements_body.text)
        assert "haven" in achievements_body.text and "any practice interviews" in achievements_body.text

        goto(driver, frontend_url, "settings.html")
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedin")))
        driver.find_element(By.ID, "authLogoutBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "account-loggedout")))


class TestPracticeRecommendation:
    """Phase 2A: the 'Recommended for You' card on practice.html. Reuses
    the existing GET /api/recommendations (Phase 9, see
    backend/tests/test_recommendations.py and test_recommendations_api.py
    for the underlying rule-engine/ownership coverage - not duplicated
    here) and the existing interview-creation flow - no new endpoint, no
    AI calls, fixed-question bank only (AI is stripped for this suite)."""

    def test_logged_out_shows_generic_baseline_and_can_start_a_real_interview(self, driver, wait, frontend_url):
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
        wait.until(lambda d: "Loading" not in reco.text)
        assert "Sign in" in reco.text
        assert "Start Recommended Session" in reco.text
        # The card's own tags state what it will start - Phase 2B check
        # that this is truthful, not just present.
        assert "Technical" in reco.text
        assert "Easy difficulty" in reco.text
        assert "5 questions" in reco.text

        driver.find_element(By.ID, "recoStartBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)
        # The actual created session must match what the card promised -
        # not just "some" fixed session.
        qcount_text = driver.find_element(By.ID, "qcount").text
        assert "Technical" in qcount_text and "Easy" in qcount_text
        assert "fixed question bank" in driver.find_element(By.ID, "sessionMode").text

    def test_logged_in_zero_history_shows_real_backend_text_and_updates_after_a_completed_interview(self, driver, wait, frontend_url):
        register(driver, wait, frontend_url, unique_email())

        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
        wait.until(lambda d: "Loading" not in reco.text)
        # This exact wording comes straight from recommendations.py's
        # _no_history_recommendation() - not frontend-invented copy.
        assert "Complete your first practice interview" in reco.text
        assert "don" in reco.text and "have any yet" in reco.text

        driver.find_element(By.ID, "recoStartBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        for i in range(1, 6):
            wait.until(lambda d, i=i: f"Question {i} of 5" in d.find_element(By.ID, "qcount").text)
            answer_box = driver.find_element(By.ID, "answer")
            answer_box.clear()
            answer_box.send_keys(f"Answer {i}.")
            driver.find_element(By.ID, "submit").click()
            if i == 5:
                wait.until(EC.alert_is_present())
                driver.switch_to.alert.accept()
        wait.until(EC.url_contains("results.html"))

        # Phase 2B: the results page reached via the recommended-session
        # path must show the actual returned result, not a blank/stuck page -
        # including the real submitted answer text once expanded (same
        # technique as test_13_interview_completion_shows_results). This is
        # a real backend session (logged in, backend reachable), so it must
        # route to the honest evaluation-aware view, never a demo-score verdict.
        result_box = wait.until(EC.visibility_of_element_located((By.ID, "result")))
        wait.until(lambda d: result_box.text.strip() != "")
        assert "Not evaluated yet" in result_box.text
        assert "Unsuccessful" not in result_box.text
        first_qa = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result details.qa")))
        driver.execute_script("arguments[0].open = true;", first_qa)
        qa_body_text = first_qa.find_element(By.CSS_SELECTOR, ".qa-body").text
        assert "Answer 1." in qa_body_text

        # Real account history changed (one completed interview, still zero
        # evaluations since AI is disabled for this suite) - the card must
        # reflect that honestly with the backend's own distinct wording,
        # never still claiming "no history" and never inventing a score.
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        reco2 = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
        wait.until(lambda d: "Loading" not in reco2.text)
        assert "Get AI feedback on a past answer" in reco2.text
        assert "Complete your first practice interview" not in reco2.text

    def test_start_recommended_session_rapid_double_click_creates_only_one_interview(self, driver, wait, frontend_url):
        # Root-caused in Phase 2B: on a fast localhost backend, the first
        # click's entire request/response cycle can complete *faster* than
        # the WebDriver round-trip needed to issue a second Python click()
        # call - so by the time the second click arrives, the transient
        # `creating` in-flight flag has already legitimately reset to
        # false, and the stale (now-hidden) card button's listener would
        # happily start a second, independent interview. The real fix is
        # pages.js's `sessionStarted` latch, set permanently once inside
        # beginSession() - not the transient in-flight flag alone - see
        # startFromCard() in prepai/js/pages.js.
        register(driver, wait, frontend_url, unique_email())

        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
        wait.until(lambda d: "Loading" not in reco.text)

        btn = driver.find_element(By.ID, "recoStartBtn")
        btn.click()
        try:
            driver.find_element(By.ID, "recoStartBtn").click()
        except Exception:
            pass  # already disabled/hidden/removed by the first click - acceptable
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        wait.until(lambda d: "of 5" in d.find_element(By.ID, "qcount").text)

        goto(driver, frontend_url, "history.html")
        account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-history-body")))
        wait.until(lambda d: account_body.text.strip() != "")
        # tbody rows only - #account-history-body also contains the table's
        # own <thead> row, which isn't an interview.
        rows = driver.find_elements(By.CSS_SELECTOR, "#account-history-body tbody tr")
        assert len(rows) == 1, f"a rapid double-click on Start Recommended Session created {len(rows)} interviews, expected 1"

    def test_question_stays_visible_after_starting_from_recommendation_card(self, driver, wait, frontend_url):
        # Same "question disappears" regression as
        # TestLoggedOutStates.test_question_stays_visible_several_seconds_
        # after_starting_and_after_each_answer, but through the
        # recommendation card's startFromCard() path (Phase 2A/2B) instead
        # of the plain setup form, since beginSession() hides both #setup
        # and #recommendation and that cleanup is a second place a stale
        # reference could in principle linger.
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
        wait.until(lambda d: "Loading" not in reco.text)
        driver.find_element(By.ID, "recoStartBtn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "session")))
        wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)

        question_text_before = driver.find_element(By.ID, "question").text
        time.sleep(3)
        assert driver.find_element(By.ID, "session").is_displayed()
        assert not driver.find_element(By.ID, "setup").is_displayed()
        assert not driver.find_element(By.ID, "recommendation").is_displayed()
        assert driver.find_element(By.ID, "question").text == question_text_before

    def test_recommendation_card_shows_error_and_retry_when_backend_unavailable(self, driver, wait, frontend_url, backend_server):
        backend_server.stop()
        try:
            goto(driver, frontend_url, "practice.html")
            wait.until(EC.visibility_of_element_located((By.ID, "setup")))
            reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
            wait.until(lambda d: "Loading" not in reco.text)
            assert "Could not load your personalized recommendation" in reco.text
            assert "Try again" in reco.text
        finally:
            backend_server.start()

    def test_recommendation_card_renders_and_starts_a_session_at_mobile_width(self, driver, wait, frontend_url):
        driver.set_window_size(390, 844)
        try:
            goto(driver, frontend_url, "practice.html")
            wait.until(EC.visibility_of_element_located((By.ID, "setup")))
            reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
            wait.until(lambda d: "Loading" not in reco.text)
            btn = driver.find_element(By.ID, "recoStartBtn")
            assert btn.is_displayed()
            assert btn.size["width"] > 300  # full-width per the <=720px CSS rule
            btn.click()
            wait.until(EC.visibility_of_element_located((By.ID, "session")))
            wait.until(lambda d: "Question 1 of 5" in d.find_element(By.ID, "qcount").text)
        finally:
            driver.set_window_size(1366, 900)

    def test_start_recommended_session_failure_does_not_leave_button_stuck(self, driver, wait, frontend_url, backend_server):
        # Phase 2B: a failed interview-creation attempt (backend unreachable
        # right at the moment Start is clicked) must recover the button -
        # never leave it disabled/"Starting..." forever, and never fail
        # silently.
        goto(driver, frontend_url, "practice.html")
        wait.until(EC.visibility_of_element_located((By.ID, "setup")))
        reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
        wait.until(lambda d: "Loading" not in reco.text)

        backend_server.stop()
        try:
            driver.find_element(By.ID, "recoStartBtn").click()
            wait.until(lambda d: d.find_element(By.ID, "recoStartBtn").get_attribute("disabled") is None)
            recovered_btn = driver.find_element(By.ID, "recoStartBtn")
            assert recovered_btn.text == "Start Recommended Session"
            assert recovered_btn.is_enabled()
            # The setup form's own error message must also appear, not a
            # silent/stuck failure.
            wait.until(lambda d: d.find_element(By.ID, "setupHint").text.strip() != "")
            # #setup must still be the visible panel, not stuck on #session.
            assert driver.find_element(By.ID, "setup").is_displayed()
        finally:
            backend_server.start()

    def test_no_horizontal_overflow_at_demo_viewport_sizes(self, driver, wait, frontend_url):
        # Phase 2B UI-quality check: the most common symptom of broken
        # responsive CSS (text/elements overflowing the viewport, forcing
        # an unwanted horizontal scrollbar) at the two sizes the demo will
        # actually be shown at.
        for width, height in [(1366, 768), (390, 844)]:
            driver.set_window_size(width, height)
            try:
                goto(driver, frontend_url, "practice.html")
                wait.until(EC.visibility_of_element_located((By.ID, "setup")))
                reco = wait.until(EC.visibility_of_element_located((By.ID, "recommendation")))
                wait.until(lambda d: "Loading" not in reco.text)
                overflow = driver.execute_script(
                    "return document.documentElement.scrollWidth - document.documentElement.clientWidth;"
                )
                assert overflow <= 1, f"horizontal overflow of {overflow}px on practice.html at {width}x{height}"
                assert driver.find_element(By.ID, "recoStartBtn").is_displayed()
            finally:
                driver.set_window_size(1366, 900)

    def test_analytics_no_horizontal_overflow_at_demo_viewport_sizes(self, driver, wait, frontend_url):
        # Same check as above, for analytics.html - this sprint added a new
        # "Your Account Overview"-style metrics section and relabeled
        # headings, both plausible sources of a new overflow regression.
        for width, height in [(1366, 768), (390, 844)]:
            driver.set_window_size(width, height)
            try:
                goto(driver, frontend_url, "analytics.html")
                account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-analytics-body")))
                wait.until(lambda d: account_body.text.strip() != "")
                overflow = driver.execute_script(
                    "return document.documentElement.scrollWidth - document.documentElement.clientWidth;"
                )
                assert overflow <= 1, f"horizontal overflow of {overflow}px on analytics.html at {width}x{height}"
                assert driver.find_element(By.ID, "metrics").is_displayed()
            finally:
                driver.set_window_size(1366, 900)

    def test_achievements_no_horizontal_overflow_at_demo_viewport_sizes(self, driver, wait, frontend_url):
        # Same check as above, for achievements.html - this sprint added a
        # new "Your Account Achievements" section and relabeled headings.
        for width, height in [(1366, 768), (390, 844)]:
            driver.set_window_size(width, height)
            try:
                goto(driver, frontend_url, "achievements.html")
                account_body = wait.until(EC.visibility_of_element_located((By.ID, "account-achievements-body")))
                wait.until(lambda d: account_body.text.strip() != "")
                overflow = driver.execute_script(
                    "return document.documentElement.scrollWidth - document.documentElement.clientWidth;"
                )
                assert overflow <= 1, f"horizontal overflow of {overflow}px on achievements.html at {width}x{height}"
                assert driver.find_element(By.ID, "featured").is_displayed()
            finally:
                driver.set_window_size(1366, 900)
