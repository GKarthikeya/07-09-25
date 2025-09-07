import os
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:
    ChromeDriverManager = None

COLLEGE_LOGIN_URL = "https://samvidha.iare.ac.in/"
ATTENDANCE_URL = "https://samvidha.iare.ac.in/home?action=course_content"

DATE_INPUT_FORMATS = [
    "%d %b, %Y",  # 03 Sep, 2025
    "%d %b %Y",   # 03 Sep 2025
]


def _parse_date(date_str: str) -> str | None:
    """Normalize date string → YYYY-MM-DD."""
    date_str = date_str.strip()
    for fmt in DATE_INPUT_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/120.0.0.0 Safari/537.36")

    # Prefer system-installed Chrome (Dockerfile provides google-chrome)
    for path in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if os.path.exists(path):
            chrome_options.binary_location = path
            break

    # Prefer system chromedriver
    service = None
    for drv in ("/usr/local/bin/chromedriver", "/usr/bin/chromedriver", "/usr/lib/chromium/chromedriver"):
        if os.path.exists(drv):
            service = Service(drv)
            break

    if service is None:
        if ChromeDriverManager is None:
            raise RuntimeError("No chromedriver found and webdriver_manager unavailable.")
        service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(service=service, options=chrome_options)


def calculate_attendance(rows, page_text=None):
    """
    Parse rows into:
      - subjects: dict of per-course stats
      - overall: total stats
      - daily: YYYY-MM-DD -> {present, absent}
      - streak: YYYY-MM-DD -> "green"/"red"
    """
    result = {
        "subjects": {},
        "overall": {"present": 0, "absent": 0, "percentage": 0.0, "success": False},
        "daily": {},
        "streak": {}
    }

    current_course_code = None
    current_course_name = None
    total_present = 0
    total_absent = 0

    def ensure_subject(code, name):
        if code not in result["subjects"]:
            result["subjects"][code] = {
                "name": name,
                "present": 0,
                "absent": 0,
                "percentage": 0.0,
                "status": ""
            }

    # --- Parse TR/TD rows ---
    for row in rows:
        text = row.text.strip()
        if not text:
            continue

        m_course = re.match(r"^\s*([A-Z]{2,}\d+)\s*[-:\u2013]\s*(.+)$", text)
        if m_course:
            current_course_code = m_course.group(1).strip()
            current_course_name = m_course.group(2).strip()
            ensure_subject(current_course_code, current_course_name)
            continue

        tds = row.find_elements(By.TAG_NAME, "td")
        if len(tds) >= 5:
            raw_cols = [td.text.strip() for td in tds]
            if any("S.NO" in c.upper() for c in raw_cols):
                continue

            sno, date_col, period_col, topics_col, status_col = raw_cols[:5]
            if not sno or not sno[0].isdigit():
                continue

            date_key = _parse_date(date_col)
            if not date_key:
                continue

            if date_key not in result["daily"]:
                result["daily"][date_key] = {"present": [], "absent": []}
            status_up = status_col.upper()
            if "PRESENT" in status_up:
                if current_course_name:
                    result["daily"][date_key]["present"].append(current_course_name)
                
                total_present += 1
                if current_course_code:
                    ensure_subject(current_course_code, current_course_name or "")
                    result["subjects"][current_course_code]["present"] += 1
            elif "ABSENT" in status_up:
                if current_course_name:
                    result["daily"][date_key]["absent"].append(current_course_name)
                    
                total_absent += 1
                if current_course_code:
                    ensure_subject(current_course_code, current_course_name or "")
                    result["subjects"][current_course_code]["absent"] += 1

    # --- Fallback if needed ---
    if not result["daily"] and page_text:
        lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            m_course = re.match(r"^\s*([A-Z]{2,}\d+)\s*[-:\u2013]\s*(.+)$", line)
            if m_course:
                current_course_code = m_course.group(1).strip()
                current_course_name = m_course.group(2).strip()
                ensure_subject(current_course_code, current_course_name)
                j = i + 1
                while j < len(lines):
                    l = lines[j]
                    if re.match(r"^\s*([A-Z]{2,}\d+)\s*[-:\u2013]\s*(.+)$", l):
                        break
                    m_row = re.search(r"(\d{1,2}\s+[A-Za-z]{3},\s+\d{4}).*(PRESENT|ABSENT)", l, re.IGNORECASE)
                    if m_row:
                        date_key = _parse_date(m_row.group(1))
                        status = m_row.group(2).upper()
                        if date_key:
                            if date_key not in result["daily"]:
                                result["daily"][date_key] = {"present": 0, "absent": 0}
                            if status == "PRESENT":
                                result["daily"][date_key]["present"] += 1
                                result["subjects"][current_course_code]["present"] += 1
                                total_present += 1
                            else:
                                result["daily"][date_key]["absent"] += 1
                                result["subjects"][current_course_code]["absent"] += 1
                                total_absent += 1
                    j += 1

    # --- Subject % and status ---
    for sub in result["subjects"].values():
        t = sub["present"] + sub["absent"]
        if t > 0:
            sub["percentage"] = round((sub["present"] / t) * 100.0, 2)
            if sub["percentage"] < 65:
                sub["status"] = "Shortage"
            elif sub["percentage"] < 75:
                sub["status"] = "Condonation"

    # --- Overall ---
    overall_total = total_present + total_absent
    if overall_total > 0:
        result["overall"] = {
            "present": total_present,
            "absent": total_absent,
            "percentage": round((total_present / overall_total) * 100.0, 2),
            "success": True
        }
    else:
        result["overall"]["success"] = False
        result["overall"]["message"] = "No attendance rows found."

    # --- Build streak data (green/red per day) ---
    for date, stats in result["daily"].items():
        if stats["absent"] > 0:
            result["streak"][date] = "red"
        else:
            result["streak"][date] = "green"

    return result


def login_and_get_attendance(username, password):
    """Login and fetch structured attendance report."""
    driver = create_driver()
    try:
        driver.get(COLLEGE_LOGIN_URL)
        time.sleep(2)

        driver.find_element(By.ID, "txt_uname").send_keys(username)
        driver.find_element(By.ID, "txt_pwd").send_keys(password)
        driver.find_element(By.ID, "but_submit").click()
        time.sleep(4)

        if "login" in driver.current_url.lower() or "Invalid username or password" in driver.page_source:
            return {"overall": {"success": False, "message": "Login failed. Please check credentials."}}

        driver.get(ATTENDANCE_URL)
        time.sleep(3)

        rows = driver.find_elements(By.TAG_NAME, "tr")
        page_text = driver.find_element(By.TAG_NAME, "body").text

        return calculate_attendance(rows, page_text=page_text)

    except Exception as e:
        return {"overall": {"success": False, "message": f"Error: {str(e)}"}}
    finally:
        try:
            driver.quit()
        except Exception:
            pass

