from pathlib import Path
import threading
import time
import os
import re
import http.server
import socketserver

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)


PORT = 8000

TEST_CASE = {
    "box1": {"x": 0, "y": 0, "width": 2, "height": 2},
    "box2": {"x": 1, "y": 1, "width": 2, "height": 2},
    "expected": True,
    "notes": "示例：两个矩形有非零面积重叠"
}


def find_index_html():
    current = Path(__file__).resolve().parent

    direct = current / "index.html"
    if direct.exists():
        return direct

    matches = list(current.rglob("index.html"))
    if matches:
        return matches[0]

    raise FileNotFoundError("未找到 index.html")


def start_http_server(root_dir, port=8000):
    handler = http.server.SimpleHTTPRequestHandler

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    def serve():
        os.chdir(root_dir)
        with ReusableTCPServer(("127.0.0.1", port), handler) as httpd:
            httpd.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(1)
    return thread


def create_driver():
    options = Options()
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    driver.maximize_window()
    return driver


def clear_and_type(elem, value):
    elem.clear()
    elem.send_keys(str(value))


def page_has_unrendered_template(driver):
    """
    检查页面中是否还存在明显未渲染的 Angular 模板变量。
    """
    body_text = driver.find_element(By.TAG_NAME, "body").text
    return bool(re.search(r"\{\{.+?\}\}", body_text))


def wait_for_page_ready(driver, wait):
    """
    等待页面基础结构与 Angular 渲染基本完成。
    """
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.test-case")))

    # 等待数字输入框出现，说明主要内容已渲染
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.test-case input[type='number']")) >= 8)

    # 给 Angular / Material 一点额外时间
    time.sleep(2)

    # 不强制完全无模板变量，因为某些隐藏节点可能保留模板文本
    has_template = page_has_unrendered_template(driver)
    if has_template:
        print("警告：页面中仍检测到部分模板变量，前端渲染可能未完全稳定。")
    else:
        print("页面模板变量已基本渲染完成。")


def set_expected_switch(driver, row, expected_value):
    switch_elem = row.find_element(By.CSS_SELECTOR, "md-switch")

    aria_checked = switch_elem.get_attribute("aria-checked")
    current_checked = str(aria_checked).lower() == "true"

    if current_checked != expected_value:
        driver.execute_script("arguments[0].click();", switch_elem)
        time.sleep(0.5)


def fill_first_test_case(driver, wait, test_case):
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.test-case")))
    time.sleep(1)

    rows = driver.find_elements(By.CSS_SELECTOR, "div.test-case")
    if not rows:
        raise RuntimeError("页面中没有找到测试用例行")

    row = rows[0]

    number_inputs = row.find_elements(By.CSS_SELECTOR, "input[type='number']")
    if len(number_inputs) < 8:
        raise RuntimeError(f"找到的数字输入框数量不足，实际为 {len(number_inputs)}，预期至少 8 个")

    values = [
        test_case["box1"]["x"],
        test_case["box1"]["y"],
        test_case["box1"]["width"],
        test_case["box1"]["height"],
        test_case["box2"]["x"],
        test_case["box2"]["y"],
        test_case["box2"]["width"],
        test_case["box2"]["height"],
    ]

    for elem, val in zip(number_inputs[:8], values):
        clear_and_type(elem, val)
        time.sleep(0.15)

    try:
        text_inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text']")
        if text_inputs:
            text_inputs[0].clear()
            text_inputs[0].send_keys(test_case.get("notes", ""))
    except Exception:
        pass

    set_expected_switch(driver, row, test_case["expected"])
    return row


def wait_for_result_update(driver, row, timeout=10):
    """
    等待结果区域真正更新，而不是立刻读取到模板文本。
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            result_items = row.find_elements(By.CSS_SELECTOR, ".test-results .result-thing")
            errors_text = ""
            try:
                errors_text = row.find_element(By.CSS_SELECTOR, ".errors").text.strip()
            except NoSuchElementException:
                errors_text = ""

            # 有结果图标，或者错误信息已不再是模板占位
            if result_items:
                if "{{" not in errors_text and "}}" not in errors_text:
                    return True
                # 有些情况下 errors 本来为空，也算可以继续
                if errors_text == "":
                    return True

        except StaleElementReferenceException:
            pass

        time.sleep(0.3)

    return False


def run_single_test(driver, row):
    play_btn = row.find_element(By.CSS_SELECTOR, "md-button.md-primary")
    driver.execute_script("arguments[0].click();", play_btn)
    ok = wait_for_result_update(driver, row, timeout=10)
    if not ok:
        print("警告：结果区域等待更新超时。")
    time.sleep(0.5)


def read_test_result(row):
    result = {
        "errors": "",
        "results_count": 0,
        "pass_icons": 0,
        "fail_icons": 0,
        "template_not_rendered": False,
    }

    try:
        errors_elem = row.find_element(By.CSS_SELECTOR, ".errors")
        result["errors"] = errors_elem.text.strip()
        if "{{" in result["errors"] or "}}" in result["errors"]:
            result["template_not_rendered"] = True
    except NoSuchElementException:
        result["errors"] = ""

    try:
        result_items = row.find_elements(By.CSS_SELECTOR, ".test-results .result-thing")
        result["results_count"] = len(result_items)

        pass_icons = row.find_elements(By.CSS_SELECTOR, ".test-results .my-primary")
        fail_icons = row.find_elements(By.CSS_SELECTOR, ".test-results .my-warn")

        result["pass_icons"] = len(pass_icons)
        result["fail_icons"] = len(fail_icons)
    except Exception:
        pass

    return result


def judge_success(result):
    """
    给出更合理的自动判断。
    """
    if result["template_not_rendered"]:
        return False, "结果区仍包含模板变量，页面渲染未稳定"

    if result["results_count"] == 0:
        return False, "没有读到任何算法结果"

    return True, "页面已执行测试并读到结果"


def main():
    driver = None
    try:
        index_path = find_index_html()
        root_dir = index_path.parent

        print(f"检测到 index.html: {index_path}")

        start_http_server(str(root_dir), PORT)
        url = f"http://127.0.0.1:{PORT}/index.html"
        print(f"访问地址: {url}")

        driver = create_driver()
        wait = WebDriverWait(driver, 20)

        driver.get(url)
        print("页面已打开")

        wait_for_page_ready(driver, wait)

        row = fill_first_test_case(driver, wait, TEST_CASE)
        print("已填写第一条测试用例")

        run_single_test(driver, row)
        print("已执行第一条测试用例")

        result = read_test_result(row)
        success, message = judge_success(result)

        print("\n===== 测试结果 =====")
        print("错误信息：", result["errors"] if result["errors"] else "无")
        print("结果总数：", result["results_count"])
        print("显示为通过的图标数：", result["pass_icons"])
        print("显示为失败的图标数：", result["fail_icons"])
        print("自动判断：", "成功" if success else "未完全成功")
        print("说明：", message)

        if result["template_not_rendered"]:
            print("提示：检测到 {{...}} 模板文本，说明 Angular 绑定结果未完全读到。")
            print("建议：检查网络是否能正常加载外部 Angular/Material 资源。")

    except TimeoutException as e:
        print("页面加载或元素等待超时：", e)
    except Exception as e:
        print("运行过程中出现异常：", e)
        raise
    finally:
        if driver is not None:
            input("\n按回车关闭浏览器...")
            driver.quit()


if __name__ == "__main__":
    main()
