import pandas as pd
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import re
from typing import List, Dict, Optional
import logging
import os

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KRXKindSeleniumScraper:
    def __init__(self, headless: bool = True, download_path: str = None):
        """
        Selenium을 사용한 KIND 크롤러 초기화
        
        Args:
            headless: 브라우저를 백그라운드에서 실행할지 여부
            download_path: 파일 다운로드 경로
        """
        self.base_url = "https://kind.krx.co.kr"
        # KIND 공시검색 메인 페이지 - 올바른 URL로 수정
        self.search_url = f"{self.base_url}/disclosure/details.do?method=searchDetailsMain"
        self.headless = headless
        self.download_path = download_path or os.getcwd()
        self.driver = None
        self.wait = None
        
    def setup_driver(self):
        """Chrome 드라이버 설정"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # 기본 옵션들
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 사용자 에이전트 설정
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # 다운로드 설정
        prefs = {
            "download.default_directory": self.download_path,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            # ChromeDriver 자동 관리 (selenium 4.x)
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 30)  # 대기시간 증가
            logger.info("Chrome 드라이버 설정 완료")
        except Exception as e:
            logger.error(f"드라이버 설정 실패: {e}")
            raise
    
    def navigate_to_search_page(self):
        """KIND 공시검색 페이지로 이동"""
        try:
            logger.info("KIND 공시검색 페이지 접속 중...")
            self.driver.get(self.search_url)
            time.sleep(5)
            
            # 페이지 로딩 완료 대기 - 더 유연한 대기조건
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.ID, "searchForm")),
                    EC.presence_of_element_located((By.CLASS_NAME, "search_02")),
                    EC.presence_of_element_located((By.NAME, "fromDate")),
                    EC.presence_of_element_located((By.XPATH, "//div[@class='sch_con']"))
                )
            )
            
            logger.info("공시검색 페이지 로딩 완료")
            return True
            
        except Exception as e:
            logger.error(f"페이지 이동 실패: {e}")
            self._save_debug_screenshot("navigate_error")
            return False
    
    def set_date_range(self, start_date: str, end_date: str):
        """기간 설정"""
        try:
            logger.info(f"날짜 설정 시작: {start_date} ~ {end_date}")
            
            # 시작일 입력 - 더 많은 셀렉터 시도
            start_date_selectors = [
                (By.NAME, "fromDate"),
                (By.ID, "fromDate"), 
                (By.XPATH, "//input[@name='fromDate']"),
                (By.XPATH, "//input[@placeholder='YYYY.MM.DD' or @placeholder='시작일']")
            ]
            
            start_date_input = None
            for selector in start_date_selectors:
                try:
                    start_date_input = self.wait.until(
                        EC.presence_of_element_located(selector)
                    )
                    break
                except TimeoutException:
                    continue
            
            if not start_date_input:
                raise Exception("시작일 입력 필드를 찾을 수 없습니다.")
            
            # 입력 필드 클리어 및 입력
            self.driver.execute_script("arguments[0].value = '';", start_date_input)
            start_date_input.clear()
            start_date_input.send_keys(start_date.replace('-', '.'))
            
            # 종료일 입력
            end_date_selectors = [
                (By.NAME, "toDate"),
                (By.ID, "toDate"),
                (By.XPATH, "//input[@name='toDate']"),
                (By.XPATH, "//input[@placeholder='YYYY.MM.DD' or @placeholder='종료일']")
            ]
            
            end_date_input = None
            for selector in end_date_selectors:
                try:
                    end_date_input = self.driver.find_element(*selector)
                    break
                except NoSuchElementException:
                    continue
            
            if not end_date_input:
                raise Exception("종료일 입력 필드를 찾을 수 없습니다.")
            
            self.driver.execute_script("arguments[0].value = '';", end_date_input)
            end_date_input.clear()
            end_date_input.send_keys(end_date.replace('-', '.'))
            
            logger.info(f"날짜 설정 완료: {start_date} ~ {end_date}")
            time.sleep(2)
            return True
            
        except Exception as e:
            logger.error(f"날짜 설정 실패: {e}")
            self._save_debug_screenshot("date_setting_error")
            return False
    
    def select_market_type(self, market_type: str = "전체"):
        """
        시장구분 선택
        
        Args:
            market_type: 선택할 시장 구분 ("전체", "유가증권", "코스닥")
        """
        try:
            logger.info(f"시장구분 선택: {market_type}")
            
            if market_type == "전체":
                # 전체 시장인 경우 별도 선택 불필요 (기본값)
                logger.info("전체 시장 선택 (기본값)")
                return True
            
            # 시장구분 라디오 버튼 선택
            market_selectors = {
                "유가증권": [
                    (By.CSS_SELECTOR, "#rWertpapier"),
                    (By.XPATH, "//*[@id='rWertpapier']"),
                    (By.ID, "rWertpapier"),
                    (By.XPATH, "//input[@id='rWertpapier']")
                ],
                "코스닥": [
                    (By.CSS_SELECTOR, "#rKosdaq"),
                    (By.XPATH, "//*[@id='rKosdaq']"),
                    (By.ID, "rKosdaq"),
                    (By.XPATH, "//input[@id='rKosdaq']")
                ]
            }
            
            if market_type not in market_selectors:
                logger.warning(f"알 수 없는 시장구분: {market_type}, 전체 시장으로 진행")
                return True
            
            selectors = market_selectors[market_type]
            success = False
            
            for i, selector in enumerate(selectors):
                try:
                    # 라디오 버튼 요소 찾기
                    radio_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(selector)
                    )
                    
                    # 스크롤하여 요소가 보이도록 함
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", radio_button)
                    time.sleep(1)
                    
                    # 라디오 버튼이 이미 선택되어 있는지 확인
                    if not radio_button.is_selected():
                        # JavaScript로 클릭 (더 안정적)
                        self.driver.execute_script("arguments[0].click();", radio_button)
                        time.sleep(0.5)
                        
                        # 선택 확인
                        if radio_button.is_selected():
                            logger.info(f"{market_type} 시장구분 선택 완료 (셀렉터 {i+1})")
                            success = True
                            break
                        else:
                            logger.debug(f"{market_type} 라디오 버튼 클릭했지만 선택되지 않음 (셀렉터 {i+1})")
                    else:
                        logger.info(f"{market_type} 시장구분 이미 선택됨")
                        success = True
                        break
                        
                except (NoSuchElementException, TimeoutException) as e:
                    logger.debug(f"{market_type} 셀렉터 {i+1} 실패: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"{market_type} 시장구분 선택 중 오류 (셀렉터 {i+1}): {e}")
                    continue
            
            if not success:
                logger.warning(f"{market_type} 시장구분 선택 실패, 전체 시장으로 진행")
                self._save_debug_screenshot(f"market_selection_error_{market_type}")
            
            time.sleep(2)
            return success
            
        except Exception as e:
            logger.error(f"시장구분 선택 실패: {e}")
            self._save_debug_screenshot("market_selection_error")
            return False

    def select_disclosure_types(self, disclosure_types: List[str] = None):
        """
        공시 유형 선택
        
        Args:
            disclosure_types: 선택할 공시 유형 리스트
                            ["투자경고종목", "불성실공시", "상장관리종목" 등]
                            None이면 투자경고종목만 선택
        """
        try:
            if disclosure_types is None:
                disclosure_types = ["투자경고종목"]

            logger.info(f"공시 유형 선택 시작: {disclosure_types}")

            # 1. 먼저 "시장조치" 탭을 클릭하여 활성화
            market_action_tab_selectors = [
                (By.ID, "dsclsType02"),
                (By.XPATH, "//*[@id='dsclsType02']"),
                (By.XPATH, "//a[@title='시장조치']"),
                (By.XPATH, "//a[contains(@onclick, 'fnDisclosureType') and contains(@onclick, '02')]"),
                (By.XPATH, "//li[contains(@class, 'tab')]/a[contains(text(), '시장조치')]")
            ]
            
            tab_clicked = False
            for selector in market_action_tab_selectors:
                try:
                    market_tab = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(selector)
                    )
                    self.driver.execute_script("arguments[0].click();", market_tab)
                    logger.info("시장조치 탭 클릭 완료")
                    tab_clicked = True
                    break
                except (NoSuchElementException, TimeoutException):
                    continue
            
            if not tab_clicked:
                logger.warning("시장조치 탭을 찾을 수 없습니다. 기본 탭에서 진행합니다.")
            
            # 탭 전환 후 대기
            time.sleep(3)
            
            # 2. 시장조치 탭이 활성화되면 체크박스들이 로드됨 - 모든 체크박스 해제
            try:
                # 시장조치 섹션 내의 체크박스만 대상으로 함
                market_section_checkboxes = self.driver.find_elements(
                    By.XPATH, 
                    "//div[@id='dsclsLayer02']//input[@type='checkbox'] | //div[contains(@class, 'market')]//input[@type='checkbox']"
                )
                
                if not market_section_checkboxes:
                    # 전체 체크박스에서 찾기
                    market_section_checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                
                for checkbox in market_section_checkboxes:
                    try:
                        if checkbox.is_selected():
                            self.driver.execute_script("arguments[0].click();", checkbox)
                    except Exception:
                        continue
                        
                time.sleep(1)
                logger.info(f"기존 체크박스 {len(market_section_checkboxes)}개 해제 완료")
            except Exception as e:
                logger.warning(f"체크박스 해제 중 오류: {e}")
            
            # 3. 원하는 공시 유형 선택
            for disclosure_type in disclosure_types:
                success = False
                
                if disclosure_type == "투자경고종목":
                    # 투자경고종목 체크박스 찾기 및 선택
                    selectors = [
                        (By.ID, "dsclsLayer02_33"),
                        (By.XPATH, "//*[@id='dsclsLayer02_33']"),
                        (By.XPATH, "//input[@value='0313']"),
                        (By.XPATH, "//label[contains(text(), '투자경고종목')]/preceding-sibling::input"),
                        (By.XPATH, "//label[contains(text(), '투자경고종목')]/..//input[@type='checkbox']"),
                        (By.XPATH, "//input[@type='checkbox' and following-sibling::label[contains(text(), '투자경고종목')]]")
                    ]
                    
                elif disclosure_type == "불성실공시":
                    selectors = [
                        (By.XPATH, "//input[@value='0314']"),
                        (By.XPATH, "//label[contains(text(), '불성실공시')]/preceding-sibling::input"),
                        (By.XPATH, "//label[contains(text(), '불성실공시')]/..//input[@type='checkbox']"),
                        (By.XPATH, "//input[@type='checkbox' and following-sibling::label[contains(text(), '불성실공시')]]")
                    ]
                    
                elif disclosure_type == "상장관리종목":
                    selectors = [
                        (By.XPATH, "//input[@value='0315']"),
                        (By.XPATH, "//label[contains(text(), '상장관리종목')]/preceding-sibling::input"),
                        (By.XPATH, "//label[contains(text(), '상장관리종목')]/..//input[@type='checkbox']"),
                        (By.XPATH, "//input[@type='checkbox' and following-sibling::label[contains(text(), '상장관리종목')]]")
                    ]
                else:
                    logger.warning(f"알 수 없는 공시 유형: {disclosure_type}")
                    continue
                
                # 체크박스 선택 시도
                for i, selector in enumerate(selectors):
                    try:
                        # 요소가 보이고 클릭 가능할 때까지 대기
                        checkbox = WebDriverWait(self.driver, 15).until(
                            EC.element_to_be_clickable(selector)
                        )
                        
                        if not checkbox.is_selected():
                            # JavaScript로 클릭 (일반 클릭이 안 될 수 있음)
                            self.driver.execute_script("arguments[0].click();", checkbox)
                            time.sleep(0.5)
                            
                            # 선택 확인
                            if checkbox.is_selected():
                                logger.info(f"{disclosure_type} 체크박스 선택 완료 (셀렉터 {i+1})")
                                success = True
                                break
                            else:
                                logger.debug(f"{disclosure_type} 체크박스 클릭했지만 선택되지 않음 (셀렉터 {i+1})")
                                
                    except (NoSuchElementException, TimeoutException) as e:
                        logger.debug(f"{disclosure_type} 셀렉터 {i+1} 실패: {e}")
                        continue
                    except Exception as e:
                        logger.debug(f"{disclosure_type} 체크박스 선택 중 오류 (셀렉터 {i+1}): {e}")
                        continue
                
                if not success:
                    logger.warning(f"{disclosure_type} 체크박스를 찾을 수 없습니다.")
                    self._save_debug_screenshot(f"checkbox_error_{disclosure_type}")
            
            time.sleep(3)
            return True
            
        except Exception as e:
            logger.error(f"공시유형 선택 실패: {e}")
            self._save_debug_screenshot("disclosure_type_error")
            return False

    def set_page_size(self, page_size: int = 100):
        """
        페이지당 표시 건수 설정
        
        Args:
            page_size: 페이지당 표시할 건수 (보통 100건으로 설정)
        """
        try:
            logger.info(f"페이지당 표시 건수를 {page_size}건으로 설정 시도...")
            
            # 페이지 사이즈 드롭다운 셀렉터
            dropdown_selectors = [
                (By.CSS_SELECTOR, "#currentPageSize"),
                (By.XPATH, "//*[@id='currentPageSize']"),
                (By.ID, "currentPageSize"),
                (By.XPATH, "//select[@id='currentPageSize']")
            ]
            
            dropdown_element = None
            for i, selector in enumerate(dropdown_selectors):
                try:
                    dropdown_element = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(selector)
                    )
                    logger.info(f"페이지 사이즈 드롭다운 발견 (셀렉터 {i+1})")
                    break
                except (TimeoutException, NoSuchElementException):
                    logger.debug(f"드롭다운 셀렉터 {i+1} 실패")
                    continue
            
            if not dropdown_element:
                logger.warning("페이지 사이즈 드롭다운을 찾을 수 없습니다. 기본값으로 진행합니다.")
                return True
            
            # 드롭다운이 보이도록 스크롤
            self.driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_element)
            time.sleep(1)
            
            # Select 객체 사용하여 옵션 선택
            try:
                from selenium.webdriver.support.ui import Select
                select = Select(dropdown_element)
                
                # 100건 옵션 선택 (여러 방법 시도)
                option_selectors = [
                    # 정확한 셀렉터
                    (By.CSS_SELECTOR, "#currentPageSize > option:nth-child(4)"),
                    (By.XPATH, "//*[@id='currentPageSize']/option[4]"),
                    # 값 기반 선택
                    (By.XPATH, "//option[@value='100']"),
                    (By.XPATH, "//option[text()='100']"),
                    (By.XPATH, "//option[contains(text(), '100')]")
                ]
                
                # 먼저 Select 객체로 시도
                try:
                    # 값으로 선택
                    select.select_by_value("100")
                    logger.info("페이지 사이즈 100건 선택 완료 (Select by value)")
                    time.sleep(2)
                    return True
                except Exception as e:
                    logger.debug(f"Select by value 실패: {e}")
                
                try:
                    # 텍스트로 선택
                    select.select_by_visible_text("100")
                    logger.info("페이지 사이즈 100건 선택 완료 (Select by text)")
                    time.sleep(2)
                    return True
                except Exception as e:
                    logger.debug(f"Select by text 실패: {e}")
                
                try:
                    # 인덱스로 선택 (4번째 옵션, 0부터 시작하므로 3)
                    select.select_by_index(3)
                    logger.info("페이지 사이즈 100건 선택 완료 (Select by index)")
                    time.sleep(2)
                    return True
                except Exception as e:
                    logger.debug(f"Select by index 실패: {e}")
                
            except Exception as e:
                logger.debug(f"Select 객체 사용 실패: {e}")
            
            # Select 객체가 실패한 경우 직접 옵션 클릭
            for i, selector in enumerate(option_selectors):
                try:
                    option_element = self.driver.find_element(*selector)
                    self.driver.execute_script("arguments[0].click();", option_element)
                    logger.info(f"페이지 사이즈 100건 선택 완료 (직접 클릭, 셀렉터 {i+1})")
                    time.sleep(2)
                    return True
                except Exception as e:
                    logger.debug(f"옵션 직접 클릭 실패 (셀렉터 {i+1}): {e}")
                    continue
            
            # 모든 방법이 실패한 경우
            logger.warning("페이지 사이즈 설정 실패, 기본값으로 진행합니다.")
            return True
            
        except Exception as e:
            logger.error(f"페이지 사이즈 설정 실패: {e}")
            self._save_debug_screenshot("page_size_setting_error")
            return True  # 실패해도 진행 계속

    def click_search_button(self):
        """검색 버튼 클릭"""
        try:
            logger.info("검색 버튼 클릭 시도...")
            
            # 검색 버튼 찾기 - 정확한 셀렉터를 우선순위로 배치
            search_button_selectors = [
                # 제공받은 정확한 셀렉터들을 최우선으로
                (By.CSS_SELECTOR, "#searchForm > section.search-group.type-00 > div > div.btn-group.type-bt > a.btn-sprite.type-00.vmiddle.search-btn"),
                (By.XPATH, "//*[@id='searchForm']/section[1]/div/div[3]/a[1]"),
                # 좀 더 간단한 버전들
                (By.CSS_SELECTOR, ".search-btn"),
                (By.CSS_SELECTOR, "a.btn-sprite.type-00.search-btn"),
                (By.CSS_SELECTOR, ".btn-group.type-bt .search-btn"),
                # 기존의 포괄적인 셀렉터들
                (By.XPATH, "//a[contains(@class, 'search-btn')]"),
                (By.XPATH, "//button[contains(text(), '검색') or contains(@value, '검색')]"),
                (By.XPATH, "//a[contains(text(), '검색') or contains(@title, '검색')]"),
                (By.XPATH, "//input[@value='검색' or @title='검색']"),
                (By.CLASS_NAME, "btn_search"),
                (By.XPATH, "//a[contains(@onclick, 'searchContents') or contains(@onclick, 'search')]"),
                (By.XPATH, "//button[@type='submit']"),
                (By.XPATH, "//div[@class='btn_area']//a[contains(text(), '검색')]")
            ]
            
            search_clicked = False
            for i, selector in enumerate(search_button_selectors):
                try:
                    search_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(selector)
                    )
                    
                    # 버튼이 화면에 보이도록 스크롤
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
                    time.sleep(1)
                    
                    # 클릭 시도
                    self.driver.execute_script("arguments[0].click();", search_button)
                    logger.info(f"검색 버튼 클릭 완료 (셀렉터 {i+1})")
                    search_clicked = True
                    break
                    
                except (TimeoutException, NoSuchElementException):
                    logger.debug(f"검색 버튼 셀렉터 {i+1} 실패")
                    continue
                except Exception as e:
                    logger.debug(f"검색 버튼 클릭 오류 (셀렉터 {i+1}): {e}")
                    continue
            
            if not search_clicked:
                raise Exception("검색 버튼을 찾을 수 없습니다.")
            
            # 검색 결과 로딩 대기
            logger.info("검색 결과 로딩 대기 중...")
            time.sleep(8)
            
            # 검색 결과 확인 - 더 포괄적인 체크
            try:
                result_found = self.wait.until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CLASS_NAME, "list_content")),
                        EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'list')]")),
                        EC.presence_of_element_located((By.XPATH, "//tr[td]")),
                        EC.presence_of_element_located((By.XPATH, "//div[@class='result']")),
                        EC.presence_of_element_located((By.XPATH, "//tbody//tr"))
                    )
                )
                logger.info("검색 결과 로딩 완료")
                return True
            except TimeoutException:
                logger.warning("검색 결과 로딩 시간 초과, 계속 진행합니다.")
                return True
                
        except Exception as e:
            logger.error(f"검색 실행 실패: {e}")
            self._save_debug_screenshot("search_error")
            return False
    
    def extract_page_data(self) -> List[Dict]:
        """현재 페이지의 데이터 추출"""
        data = []
        
        try:
            logger.info("페이지 데이터 추출 시작...")
            
            # 결과 테이블 행 찾기
            table_rows = []
            
            # 다양한 테이블 구조 시도 - 모든 데이터 행 포함
            selectors = [
                "//tbody//tr[td]",  # tbody 내의 모든 tr 우선
                "//table//tr[td]",  # position()>1 제거하여 모든 행 포함
                "//div[@class='list_content']//tr[td]",
                "//tr[td and count(td)>=3]",  # 최소 3개 컬럼
                "//table[@class='list']//tr[td]",
                "//div[contains(@class, 'result')]//tr[td]"
            ]
            
            for selector in selectors:
                try:
                    rows = self.driver.find_elements(By.XPATH, selector)
                    if rows and len(rows) > 0:
                        # 헤더 행이 아닌 실제 데이터 행만 필터링
                        actual_rows = []
                        for i, row in enumerate(rows):
                            try:
                                cells = row.find_elements(By.TAG_NAME, "td")
                                if len(cells) < 3:  # 최소 3개 컬럼 필요
                                    continue
                                
                                first_cell = cells[0]
                                cell_text = first_cell.text.strip().lower()
                                
                                # 헤더 행 판별 로직 개선
                                is_header = False
                                
                                # 명확한 헤더 텍스트들
                                header_keywords = ['번호', 'no', '순번', '시간', 'time', '접수번호', '공시제목', '회사명', '제출인']
                                if any(keyword in cell_text for keyword in header_keywords):
                                    is_header = True
                                
                                # 첫 번째 셀이 비어있거나 너무 짧은 경우
                                if not cell_text or len(cell_text.strip()) == 0:
                                    continue
                                
                                # 헤더가 아니면 데이터 행으로 포함
                                if not is_header:
                                    actual_rows.append(row)
                                    logger.debug(f"데이터 행 {i+1} 포함: 첫 번째 셀 = '{cell_text[:20]}...'")
                                else:
                                    logger.debug(f"헤더 행 {i+1} 제외: '{cell_text}'")
                                    
                            except Exception as e:
                                logger.debug(f"행 {i+1} 처리 중 오류: {e}")
                                continue
                        
                        if actual_rows:
                            table_rows = actual_rows
                            logger.info(f"테이블 행 {len(actual_rows)}개 발견 (전체 {len(rows)}개 중, 셀렉터: {selector})")
                            
                            # 첫 번째와 마지막 행의 정보 로깅
                            if len(actual_rows) > 0:
                                try:
                                    first_row_cells = actual_rows[0].find_elements(By.TAG_NAME, "td")
                                    first_row_text = [cell.text.strip()[:20] for cell in first_row_cells[:3]]
                                    logger.info(f"첫 번째 데이터 행: {first_row_text}")
                                    
                                    if len(actual_rows) > 1:
                                        last_row_cells = actual_rows[-1].find_elements(By.TAG_NAME, "td")
                                        last_row_text = [cell.text.strip()[:20] for cell in last_row_cells[:3]]
                                        logger.info(f"마지막 데이터 행: {last_row_text}")
                                except Exception as e:
                                    logger.debug(f"행 정보 로깅 실패: {e}")
                            break
                except Exception as e:
                    logger.debug(f"셀렉터 {selector} 실패: {e}")
                    continue
            
            if not table_rows:
                # 검색 결과가 없는 경우 체크
                no_result_indicators = [
                    "//div[contains(text(), '검색결과가 없습니다')]",
                    "//div[contains(text(), '조회된 데이터가 없습니다')]",
                    "//td[contains(text(), '검색된 결과가 없습니다')]",
                    "//span[contains(text(), '데이터가 없습니다')]"
                ]
                
                for indicator in no_result_indicators:
                    try:
                        if self.driver.find_elements(By.XPATH, indicator):
                            logger.info("검색 결과가 없습니다.")
                            return []
                    except:
                        continue
                
                logger.warning("테이블 행을 찾을 수 없습니다.")
                self._save_debug_screenshot("no_table_rows")
                return []
            
            for i, row in enumerate(table_rows):
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cols) < 3:  # 최소 3개 컬럼은 있어야 함
                        continue
                    
                    # 데이터 추출 - 다양한 컬럼 구조 대응
                    if len(cols) >= 5:
                        # 번호, 시간, 회사명, 공시제목, 제출인 형태
                        row_num = cols[0].text.strip()
                        time_text = cols[1].text.strip()
                        company_name = cols[2].text.strip()
                        title_col = cols[3]
                        submitter = cols[4].text.strip() if len(cols) > 4 else ""
                        
                    elif len(cols) == 4:
                        # 시간, 회사명, 공시제목, 제출인 형태
                        row_num = str(i + 1)
                        time_text = cols[0].text.strip()
                        company_name = cols[1].text.strip()
                        title_col = cols[2]
                        submitter = cols[3].text.strip()
                        
                    elif len(cols) == 3:
                        # 시간, 회사명, 공시제목 형태
                        row_num = str(i + 1)
                        time_text = cols[0].text.strip()
                        company_name = cols[1].text.strip()
                        title_col = cols[2]
                        submitter = ""
                    else:
                        continue
                    
                    # 공시제목 및 링크 추출
                    title_links = title_col.find_elements(By.TAG_NAME, "a")
                    if title_links:
                        title_element = title_links[0]
                        title = title_element.text.strip()
                        onclick_attr = title_element.get_attribute("onclick")
                        href_attr = title_element.get_attribute("href")
                        disclosure_link = self._extract_disclosure_link(onclick_attr, href_attr)
                    else:
                        title = title_col.text.strip()
                        disclosure_link = None
                    
                    # 빈 데이터나 헤더 행 스킵
                    if not title or not company_name or title.lower() in ['공시제목', '제목', 'title']:
                        continue
                    
                    # 시간 정보가 없거나 이상한 경우 스킵
                    if not time_text or len(time_text) < 8:
                        continue
                    
                    # 공시제목 분석
                    title_analysis = self._analyze_title(title)
                    
                    data_item = {
                        'row_num': row_num,
                        'datetime': time_text,
                        'company_name': company_name,
                        'title': title,
                        'submitter': submitter,
                        'disclosure_link': disclosure_link,
                        'is_redesignation': title_analysis['is_redesignation'],
                        'is_preferred_stock': title_analysis['is_preferred_stock'],
                        'designation_type': title_analysis['designation_type']
                    }
                    
                    data.append(data_item)
                    
                except Exception as e:
                    logger.debug(f"행 {i} 처리 중 오류: {e}")
                    continue
            
            logger.info(f"현재 페이지에서 {len(data)}개 항목 추출")
            return data
            
        except Exception as e:
            logger.error(f"페이지 데이터 추출 실패: {e}")
            self._save_debug_screenshot("extract_data_error")
            return []
    
    def get_current_page_number(self) -> int:
        """현재 페이지 번호 확인"""
        try:
            # 현재 페이지를 나타내는 요소 찾기 - 더 포괄적인 셀렉터
            current_page_selectors = [
                "//a[contains(@class, 'current') or contains(@class, 'on') or contains(@class, 'active')]",
                "//span[contains(@class, 'current') or contains(@class, 'on') or contains(@class, 'active')]", 
                "//strong[contains(@class, 'current') or contains(@class, 'on')]",
                "//li[contains(@class, 'on') or contains(@class, 'current')]//a",
                "//div[@class='paging']//strong",
                "//div[contains(@class, 'page')]//strong"
            ]
            
            for selector in current_page_selectors:
                try:
                    current_elements = self.driver.find_elements(By.XPATH, selector)
                    for element in current_elements:
                        page_text = element.text.strip()
                        if page_text.isdigit() and int(page_text) > 0:
                            return int(page_text)
                except NoSuchElementException:
                    continue
            
            # URL에서 페이지 번호 추출 시도
            try:
                current_url = self.driver.current_url
                page_match = re.search(r'page[Nn]o?=(\d+)', current_url)
                if page_match:
                    return int(page_match.group(1))
            except:
                pass
            
            # 기본값 반환
            return 1
            
        except Exception as e:
            logger.debug(f"현재 페이지 번호 확인 실패: {e}")
            return 1
    
    def navigate_to_next_page(self) -> bool:
        """다음 페이지로 이동"""
        try:
            current_page = self.get_current_page_number()
            logger.info(f"현재 페이지: {current_page}, 다음 페이지로 이동 시도...")
            
            # 다음 페이지 버튼 찾기 - 더 포괄적인 셀렉터
            next_page_selectors = [
                f"//a[text()='{current_page + 1}' and not(contains(@class, 'disabled'))]",
                "//a[contains(@onclick, 'goPage') and contains(text(), '다음')]",
                "//a[contains(@class, 'next') and not(contains(@class, 'disabled'))]",
                f"//a[contains(@onclick, 'goPage({current_page + 1})')]",
                "//a[contains(@title, '다음')]",
                "//button[contains(text(), '다음')]",
                f"//a[@href and contains(@href, 'page={current_page + 1}')]"
            ]
            
            next_clicked = False
            for i, selector in enumerate(next_page_selectors):
                try:
                    next_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(selector)
                    )
                    
                    # 버튼이 실제로 클릭 가능한지 확인
                    if next_button.is_enabled() and next_button.is_displayed():
                        # 스크롤하여 버튼이 보이도록 함
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                        time.sleep(1)
                        
                        self.driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(4)  # 페이지 로딩 대기
                        
                        # 페이지 변경 확인
                        new_page = self.get_current_page_number()
                        if new_page > current_page:
                            logger.info(f"페이지 {new_page}로 이동 완료 (셀렉터 {i+1})")
                            return True
                        else:
                            logger.debug(f"페이지 이동 실패 - 페이지 번호 변경되지 않음 (셀렉터 {i+1})")
                            continue
                            
                except (NoSuchElementException, TimeoutException):
                    logger.debug(f"다음 페이지 셀렉터 {i+1} 실패")
                    continue
                except Exception as e:
                    logger.debug(f"다음 페이지 이동 오류 (셀렉터 {i+1}): {e}")
                    continue
            
            # 페이지 번호 직접 클릭 시도
            try:
                logger.info("페이지 번호 직접 클릭 시도...")
                page_links = self.driver.find_elements(By.XPATH, "//a[contains(@onclick, 'goPage') or @href]")
                for link in page_links:
                    try:
                        onclick = link.get_attribute("onclick")
                        href = link.get_attribute("href")
                        link_text = link.text.strip()
                        
                        # onclick 속성에서 페이지 번호 추출
                        if onclick:
                            match = re.search(r'goPage\((\d+)\)', onclick)
                            if match:
                                page_num = int(match.group(1))
                                if page_num == current_page + 1:
                                    self.driver.execute_script("arguments[0].click();", link)
                                    time.sleep(4)
                                    new_page = self.get_current_page_number()
                                    if new_page > current_page:
                                        logger.info(f"페이지 {page_num}로 이동 (onclick)")
                                        return True
                        
                        # href 속성에서 페이지 번호 추출
                        if href and 'page' in href:
                            page_match = re.search(r'page[Nn]o?=(\d+)', href)
                            if page_match:
                                page_num = int(page_match.group(1))
                                if page_num == current_page + 1:
                                    self.driver.execute_script("arguments[0].click();", link)
                                    time.sleep(4)
                                    new_page = self.get_current_page_number()
                                    if new_page > current_page:
                                        logger.info(f"페이지 {page_num}로 이동 (href)")
                                        return True
                        
                        # 링크 텍스트가 다음 페이지 번호인 경우
                        if link_text.isdigit() and int(link_text) == current_page + 1:
                            self.driver.execute_script("arguments[0].click();", link)
                            time.sleep(4)
                            new_page = self.get_current_page_number()
                            if new_page > current_page:
                                logger.info(f"페이지 {link_text}로 이동 (텍스트)")
                                return True
                                
                    except Exception as e:
                        logger.debug(f"페이지 링크 처리 오류: {e}")
                        continue
            except Exception as e:
                logger.debug(f"페이지 번호 직접 클릭 실패: {e}")
            
            logger.info("더 이상 다음 페이지가 없습니다.")
            return False
            
        except Exception as e:
            logger.error(f"다음 페이지 이동 실패: {e}")
            self._save_debug_screenshot("pagination_error")
            return False
    
    def scrape_period_data(self, start_date: str, end_date: str, 
                          disclosure_types: List[str] = None, 
                          max_pages: int = None,
                          market_type: str = "전체") -> List[Dict]:
        """특정 기간의 데이터 수집"""
        all_data = []
        
        try:
            logger.info(f"기간별 데이터 수집 시작: {start_date} ~ {end_date}")
            
            # 검색 페이지로 이동
            if not self.navigate_to_search_page():
                return []
            
            # 날짜 설정
            if not self.set_date_range(start_date, end_date):
                return []
            
            # 시장구분 선택
            if not self.select_market_type(market_type):
                return []
            
            # 공시 유형 선택
            if not self.select_disclosure_types(disclosure_types):
                return []
            
            # 페이지당 표시 건수를 100건으로 설정 (검색 전에 설정)
            self.set_page_size(100)
            
            # 검색 실행
            if not self.click_search_button():
                return []
            
            page_num = 1
            consecutive_empty_pages = 0
            max_consecutive_empty = 3  # 연속으로 빈 페이지가 3번 나오면 중단
            
            while True:
                logger.info(f"페이지 {page_num} 데이터 수집 중...")
                
                # 최대 페이지 수 제한 체크
                if max_pages and page_num > max_pages:
                    logger.info(f"최대 페이지 수({max_pages}) 도달, 수집 중단")
                    break
                
                # 현재 페이지 데이터 추출
                page_data = self.extract_page_data()
                
                if not page_data:
                    consecutive_empty_pages += 1
                    logger.warning(f"페이지 {page_num}에서 데이터 없음 (연속 {consecutive_empty_pages}회)")
                    
                    if consecutive_empty_pages >= max_consecutive_empty:
                        logger.info("연속으로 빈 페이지가 나타나 수집을 중단합니다.")
                        break
                else:
                    consecutive_empty_pages = 0  # 데이터가 있으면 카운터 리셋
                    all_data.extend(page_data)
                    logger.info(f"페이지 {page_num}에서 {len(page_data)}개 항목 수집")
                
                # 다음 페이지로 이동
                if not self.navigate_to_next_page():
                    logger.info("더 이상 다음 페이지가 없어 수집을 완료합니다.")
                    break
                
                page_num += 1
                
                # 페이지 간 대기 (과부하 방지)
                time.sleep(2)
                
                # 너무 많은 페이지를 수집하지 않도록 안전장치
                if page_num > 100:
                    logger.warning("100페이지 초과, 안전을 위해 수집을 중단합니다.")
                    break
            
            logger.info(f"기간 {start_date}~{end_date}: {len(all_data)}개 항목 수집 완료")
            return all_data
            
        except Exception as e:
            logger.error(f"기간별 데이터 수집 실패: {e}")
            self._save_debug_screenshot("period_scraping_error")
            return all_data
    
    def split_date_range(self, start_date: str, end_date: str, 
                        max_months: int = 6) -> List[tuple]:
        """긴 기간을 작은 단위로 분할"""
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            date_ranges = []
            current_start = start_dt
            
            while current_start < end_dt:
                # max_months 만큼 더한 날짜 계산
                if current_start.month + max_months <= 12:
                    current_end = current_start.replace(month=current_start.month + max_months)
                else:
                    months_over = (current_start.month + max_months) - 12
                    current_end = current_start.replace(year=current_start.year + 1, month=months_over)
                
                # 전체 종료일을 넘지 않도록
                if current_end > end_dt:
                    current_end = end_dt
                
                date_ranges.append((
                    current_start.strftime('%Y-%m-%d'),
                    current_end.strftime('%Y-%m-%d')
                ))
                
                current_start = current_end + timedelta(days=1)
            
            return date_ranges
            
        except Exception as e:
            logger.error(f"날짜 분할 실패: {e}")
            return [(start_date, end_date)]
    
    def scrape_investment_warning_stocks(self, 
                                       start_date: str, 
                                       end_date: str,
                                       disclosure_types: List[str] = None,
                                       output_filename: str = None,
                                       split_long_periods: bool = True,
                                       max_pages_per_period: int = None,
                                       market_type: str = "전체") -> pd.DataFrame:
        """
        투자경고종목 데이터 스크래핑 메인 함수
        
        Args:
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            disclosure_types: 공시 유형 리스트
            output_filename: 출력 파일명
            split_long_periods: 긴 기간을 분할할지 여부
            max_pages_per_period: 기간별 최대 수집 페이지 수
            market_type: 시장구분 ("전체", "유가증권", "코스닥")
        """
        logger.info(f"투자경고종목 데이터 수집 시작")
        logger.info(f"기간: {start_date} ~ {end_date}")
        logger.info(f"공시 유형: {disclosure_types or ['투자경고종목']}")
        logger.info(f"시장구분: {market_type}")
        
        try:
            # 드라이버 설정
            if not self.driver:
                self.setup_driver()
            
            all_data = []
            
            # 긴 기간인 경우 분할 처리
            if split_long_periods:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                days_diff = (end_dt - start_dt).days
                
                if days_diff > 365:  # 1년 이상인 경우 분할
                    date_ranges = self.split_date_range(start_date, end_date, max_months=6)
                    logger.info(f"긴 기간을 {len(date_ranges)}개 구간으로 분할하여 처리")
                    
                    for i, (range_start, range_end) in enumerate(date_ranges):
                        logger.info(f"구간 {i+1}/{len(date_ranges)}: {range_start} ~ {range_end}")
                        try:
                            period_data = self.scrape_period_data(
                                range_start, range_end, disclosure_types, max_pages_per_period, market_type
                            )
                            all_data.extend(period_data)
                            
                            # 구간 간 대기 (서버 부하 방지)
                            if i < len(date_ranges) - 1:
                                logger.info("구간 간 대기 중...")
                                time.sleep(10)
                        except Exception as e:
                            logger.error(f"구간 {i+1} 처리 중 오류: {e}")
                            continue
                else:
                    all_data = self.scrape_period_data(start_date, end_date, disclosure_types, max_pages_per_period, market_type)
            else:
                all_data = self.scrape_period_data(start_date, end_date, disclosure_types, max_pages_per_period, market_type)
            
            if not all_data:
                logger.warning("수집된 데이터가 없습니다.")
                return pd.DataFrame()
            
            # 데이터프레임 생성 및 처리
            df = pd.DataFrame(all_data)
            
            # 중복 제거 (동일한 공시가 여러 번 수집될 수 있음)
            original_count = len(df)
            df = df.drop_duplicates(subset=['datetime', 'company_name', 'title'])
            deduplicated_count = len(df)
            
            if original_count > deduplicated_count:
                logger.info(f"중복 제거: {original_count - deduplicated_count}개 제거")
            
            # 날짜순 정렬
            try:
                df['datetime_sort'] = pd.to_datetime(df['datetime'], errors='coerce')
                df = df.sort_values('datetime_sort', ascending=False)
                df = df.drop('datetime_sort', axis=1)
            except Exception as e:
                logger.warning(f"날짜 정렬 실패: {e}")
            
            # 파일 저장
            if output_filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_filename = f"investment_warning_stocks_{start_date}_{end_date}_{timestamp}.csv"
            
            self.save_to_csv(df, output_filename)
            
            logger.info(f"총 {len(df)}개 항목 수집 완료")
            return df
            
        except Exception as e:
            logger.error(f"스크래핑 실패: {e}")
            self._save_debug_screenshot("main_scraping_error")
            return pd.DataFrame()
            
        finally:
            self.close_driver()
    
    def _extract_disclosure_link(self, onclick_text: str, href_text: str) -> Optional[str]:
        """onclick 속성 또는 href 속성에서 공시상세 링크 추출"""
        try:
            if onclick_text and "openDisclsViewer" in onclick_text:
                pattern = r"openDisclsViewer\('([^']*)',\s*'([^']*)',\s*'([^']*)'"
                match = re.search(pattern, onclick_text)
                
                if match:
                    acptno, docno, viewerhost = match.groups()
                    link = f"{self.base_url}/common/disclsviewer.do?method=search&acptno={acptno}&docno={docno}&viewerhost={viewerhost}&viewerport="
                    return link
            elif href_text and "disclsviewer.do" in href_text:
                # href 속성에서 링크 추출
                link_match = re.search(r"disclsviewer\.do\?method=search&acptno=([^&]+)&docno=([^&]+)&viewerhost=([^&]+)", href_text)
                if link_match:
                    acptno, docno, viewerhost = link_match.groups()
                    link = f"{self.base_url}/common/disclsviewer.do?method=search&acptno={acptno}&docno={docno}&viewerhost={viewerhost}&viewerport="
                    return link
        except Exception as e:
            logger.debug(f"공시 링크 추출 실패: {e}")
        
        return None
    
    def _analyze_title(self, title: str) -> Dict[str, any]:
        """공시제목 분석"""
        analysis = {
            'is_redesignation': False,
            'is_preferred_stock': False,
            'designation_type': 'unknown'
        }
        
        # 재지정 여부 확인
        redesignation_keywords = ['재지정', '재선정', '재대상']
        analysis['is_redesignation'] = any(keyword in title for keyword in redesignation_keywords)
        
        # 우선주 여부 확인
        preferred_keywords = ['우선주', '우선株', 'preferred']
        analysis['is_preferred_stock'] = any(keyword in title.lower() for keyword in preferred_keywords)
        
        # 지정 유형 분석
        if '투자경고' in title:
            if '지정' in title and '해제' not in title:
                analysis['designation_type'] = 'designation'
            elif '해제' in title:
                analysis['designation_type'] = 'cancellation'
            else:
                analysis['designation_type'] = 'other'
        
        return analysis
    
    def save_to_csv(self, df: pd.DataFrame, filename: str):
        """데이터를 CSV 파일로 저장"""
        if df.empty:
            logger.warning("저장할 데이터가 없습니다.")
            return
        
        try:
            # 날짜/시간 컬럼 정리
            if 'datetime' in df.columns:
                # datetime 컬럼을 날짜와 시간으로 분리
                try:
                    # 다양한 날짜 형식 처리
                    df_copy = df.copy()
                    
                    # 공백으로 분리 시도
                    split_result = df_copy['datetime'].str.split(' ', expand=True)
                    if split_result.shape[1] >= 2:
                        df_copy['date'] = split_result[0]
                        df_copy['time'] = split_result[1]
                    else:
                        # 분리가 안되면 전체를 날짜로
                        df_copy['date'] = df_copy['datetime']
                        df_copy['time'] = ''
                    
                    # 날짜 형식 정리 (YYYY.MM.DD -> YYYY-MM-DD)
                    df_copy['date'] = df_copy['date'].str.replace('.', '-', regex=False)
                    df_copy['date'] = pd.to_datetime(df_copy['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                    
                    # 원본 데이터프레임에 적용
                    df['date'] = df_copy['date']
                    df['time'] = df_copy['time']
                    
                except Exception as e:
                    logger.warning(f"날짜/시간 분리 실패: {e}")
                    df['date'] = df['datetime']
                    df['time'] = ''
            
            # 컬럼 순서 정리
            base_columns = ['row_num', 'date', 'time', 'company_name', 'title', 'submitter']
            analysis_columns = ['is_redesignation', 'is_preferred_stock', 'designation_type']
            link_columns = ['disclosure_link']
            
            column_order = base_columns + analysis_columns + link_columns
            available_columns = [col for col in column_order if col in df.columns]
            
            # 누락된 컬럼이 있으면 추가
            remaining_columns = [col for col in df.columns if col not in available_columns]
            available_columns.extend(remaining_columns)
            
            df_output = df[available_columns]
            
            # 파일 경로 처리
            if not os.path.isabs(filename):
                filename = os.path.join(self.download_path, filename)
            
            # CSV 저장
            df_output.to_csv(filename, index=False, encoding='utf-8-sig')
            logger.info(f"데이터 저장 완료: {filename} ({len(df_output)}개 항목)")
            
            # 간단한 통계 정보 출력
            if 'designation_type' in df_output.columns:
                logger.info("지정 유형별 분포:")
                type_counts = df_output['designation_type'].value_counts()
                for type_name, count in type_counts.items():
                    logger.info(f"  {type_name}: {count}개")
            
        except Exception as e:
            logger.error(f"CSV 저장 실패: {e}")
            
    def get_summary_stats(self, df: pd.DataFrame) -> Dict:
        """수집된 데이터의 요약 통계 반환"""
        if df.empty:
            return {"total": 0}
        
        stats = {
            "total": len(df),
            "companies": df['company_name'].nunique() if 'company_name' in df.columns else 0,
            "date_range": {
                "start": None,
                "end": None
            }
        }
        
        # 날짜 범위 계산
        if 'date' in df.columns:
            try:
                dates = pd.to_datetime(df['date'], errors='coerce').dropna()
                if not dates.empty:
                    stats["date_range"]["start"] = dates.min().strftime('%Y-%m-%d')
                    stats["date_range"]["end"] = dates.max().strftime('%Y-%m-%d')
            except:
                pass
        
        # 지정 유형별 분포
        if 'designation_type' in df.columns:
            stats["designation_types"] = df['designation_type'].value_counts().to_dict()
        
        # 재지정 여부 분포
        if 'is_redesignation' in df.columns:
            stats["redesignation_ratio"] = df['is_redesignation'].mean()
        
        # 우선주 여부 분포
        if 'is_preferred_stock' in df.columns:
            stats["preferred_stock_ratio"] = df['is_preferred_stock'].mean()
        
        # 상위 회사들
        if 'company_name' in df.columns:
            stats["top_companies"] = df['company_name'].value_counts().head(10).to_dict()
        
        return stats

    def close_driver(self):
        """드라이버 종료"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("브라우저 드라이버 종료")
            except Exception as e:
                logger.warning(f"드라이버 종료 중 오류: {e}")

    def _save_debug_screenshot(self, filename_prefix: str):
        """디버그용 스크린샷 저장"""
        try:
            if self.driver:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(self.download_path, f"{filename_prefix}_{timestamp}.png")
                self.driver.save_screenshot(screenshot_path)
                logger.warning(f"스크린샷 저장: {screenshot_path}")
        except Exception as e:
            logger.error(f"스크린샷 저장 실패: {e}")


# 장기간 데이터 수집 함수
def scrape_multi_year_data(start_year: int, end_year: int, 
                          disclosure_types: List[str] = None,
                          headless: bool = True) -> pd.DataFrame:
    """
    여러 년도 데이터를 효율적으로 수집
    
    Args:
        start_year: 시작 연도
        end_year: 종료 연도 
        disclosure_types: 공시 유형 리스트
        headless: 헤드리스 모드 여부
    """
    all_dataframes = []
    
    for year in range(start_year, end_year + 1):
        logger.info(f"{year}년 데이터 수집 시작...")
        
        scraper = KRXKindSeleniumScraper(headless=headless)
        
        try:
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"
            
            df = scraper.scrape_investment_warning_stocks(
                start_date=start_date,
                end_date=end_date,
                disclosure_types=disclosure_types,
                output_filename=f"investment_warning_{year}.csv",
                split_long_periods=True
            )
            
            if not df.empty:
                all_dataframes.append(df)
                logger.info(f"{year}년 데이터 수집 완료: {len(df)}개 항목")
            else:
                logger.warning(f"{year}년 데이터가 없습니다.")
            
            # 연도별 처리 후 대기 (서버 부하 방지)
            time.sleep(10)
            
        except Exception as e:
            logger.error(f"{year}년 데이터 수집 실패: {e}")
        
        finally:
            scraper.close_driver()
    
    # 모든 데이터 통합
    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        
        # 중복 제거
        combined_df = combined_df.drop_duplicates(subset=['datetime', 'company_name', 'title'])
        
        # 날짜순 정렬
        combined_df = combined_df.sort_values('datetime')
        
        # 통합 파일 저장
        filename = f"investment_warning_stocks_{start_year}_{end_year}_combined.csv"
        combined_df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        logger.info(f"전체 데이터 통합 완료: {filename} ({len(combined_df)}개 항목)")
        return combined_df
    
    return pd.DataFrame()

# 고급 사용 예제
def advanced_scraping_example():
    """고급 크롤링 예제 - 다양한 옵션 활용"""
    
    # 1. 최근 6개월 투자경고종목 + 불성실공시 데이터 수집
    logger.info("=== 최근 6개월 다중 공시유형 데이터 수집 ===")
    scraper = KRXKindSeleniumScraper(headless=True)
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    
    df_multi = scraper.scrape_investment_warning_stocks(
        start_date=start_date,
        end_date=end_date,
        disclosure_types=["투자경고종목", "불성실공시"],
        output_filename="multi_disclosure_6months.csv"
    )
    
    # 2. 과거 3년간 투자경고종목만 수집 (자동 분할)
    logger.info("=== 과거 3년간 투자경고종목 데이터 수집 ===")
    scraper2 = KRXKindSeleniumScraper(headless=True)
    
    start_date_3y = (datetime.now() - timedelta(days=1095)).strftime('%Y-%m-%d')
    
    df_3years = scraper2.scrape_investment_warning_stocks(
        start_date=start_date_3y,
        end_date=end_date,
        disclosure_types=["투자경고종목"],
        output_filename="investment_warning_3years.csv",
        split_long_periods=True
    )
    
    # 3. 결과 분석
    if not df_multi.empty:
        print(f"\n다중 공시유형 6개월: {len(df_multi)}개 항목")
        print("공시유형별 분포:")
        print(df_multi['designation_type'].value_counts())
    
    if not df_3years.empty:
        print(f"\n투자경고종목 3년간: {len(df_3years)}개 항목")
        print("연도별 분포:")
        df_3years['year'] = pd.to_datetime(df_3years['date']).dt.year
        print(df_3years['year'].value_counts().sort_index())

# 실행 가이드
if __name__ == "__main__":
    print("=== KRX KIND 투자경고종목 크롤러 ===")
    print("\n사용 가능한 함수:")
    print("1. 기본 사용: scraper.scrape_investment_warning_stocks()")
    print("2. 다년도 수집: scrape_multi_year_data()")
    print("3. 고급 예제: advanced_scraping_example()")
    
    print("\n필요한 라이브러리:")
    print("pip install selenium pandas")
    
    print("\n주의사항:")
    print("- Chrome 브라우저가 설치되어 있어야 합니다")
    print("- 첫 실행 시 headless=False로 설정하여 동작 확인을 권장합니다")
    print("- 긴 기간 수집 시 자동으로 기간을 분할하여 처리합니다")
    print("- IP 차단 방지를 위해 적절한 대기시간이 적용됩니다")
    print("- 오류 발생 시 스크린샷이 자동으로 저장됩니다")
    
    print("\n=== 사용 예제 실행 ===")
    
    # 사용자 입력 받기
    try:
        print("\n1. 테스트 실행 (최근 7일)")
        print("2. 사용자 지정 기간")
        print("3. 종료")
        
        choice = input("\n선택하세요 (1-3): ").strip()
        
        if choice == "1":
            # 테스트 실행
            print("\n테스트 실행을 시작합니다...")
            scraper = KRXKindSeleniumScraper(headless=False)  # 테스트시 headless=False 권장
            
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            print("\n시장구분을 선택하세요:")
            print("1. 전체")
            print("2. 유가증권")
            print("3. 코스닥")
            
            market_choice = input("시장구분을 선택하세요 (1-3): ").strip()
            market_types_map = {
                "1": "전체",
                "2": "유가증권", 
                "3": "코스닥"
            }
            market_type = market_types_map.get(market_choice, "전체")
            
            df = scraper.scrape_investment_warning_stocks(
                start_date=start_date,
                end_date=end_date,
                disclosure_types=["투자경고종목"],
                max_pages_per_period=5,  # 테스트용으로 5페이지만
                market_type=market_type
            )
            
            if not df.empty:
                print(f"\n수집 완료: {len(df)}개 항목")
                print("\n수집된 데이터 미리보기:")
                print(df[['datetime', 'company_name', 'title']].head(10))
            else:
                print("수집된 데이터가 없습니다.")
                
        elif choice == "2":
            # 사용자 지정 기간
            start_date = input("시작일을 입력하세요 (YYYY-MM-DD): ").strip()
            end_date = input("종료일을 입력하세요 (YYYY-MM-DD): ").strip()
            
            # 날짜 형식 검증
            try:
                datetime.strptime(start_date, '%Y-%m-%d')
                datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                print("잘못된 날짜 형식입니다. YYYY-MM-DD 형식으로 입력해주세요.")
                exit(1)
            
            print("\n사용 가능한 공시 유형:")
            print("1. 투자경고종목")
            print("2. 불성실공시")
            print("3. 상장관리종목")
            print("4. 전체 (투자경고종목 + 불성실공시 + 상장관리종목)")
            
            type_choice = input("공시 유형을 선택하세요 (1-4): ").strip()
            
            disclosure_types_map = {
                "1": ["투자경고종목"],
                "2": ["불성실공시"],
                "3": ["상장관리종목"],
                "4": ["투자경고종목", "불성실공시", "상장관리종목"]
            }
            
            disclosure_types = disclosure_types_map.get(type_choice, ["투자경고종목"])
            
            print("\n시장구분을 선택하세요:")
            print("1. 전체")
            print("2. 유가증권")
            print("3. 코스닥")
            
            market_choice = input("시장구분을 선택하세요 (1-3): ").strip()
            market_types_map = {
                "1": "전체",
                "2": "유가증권", 
                "3": "코스닥"
            }
            market_type = market_types_map.get(market_choice, "전체")
            
            headless_choice = input("백그라운드 실행하시겠습니까? (y/n): ").strip().lower()
            headless = headless_choice == 'y'
            
            print(f"\n데이터 수집을 시작합니다...")
            print(f"기간: {start_date} ~ {end_date}")
            print(f"공시 유형: {disclosure_types}")
            print(f"시장구분: {market_type}")
            print(f"백그라운드 실행: {'예' if headless else '아니오'}")
            
            scraper = KRXKindSeleniumScraper(headless=headless)
            
            df = scraper.scrape_investment_warning_stocks(
                start_date=start_date,
                end_date=end_date,
                disclosure_types=disclosure_types,
                market_type=market_type
            )
            
            if not df.empty:
                print(f"\n수집 완료: {len(df)}개 항목")
                print("\n회사별 공시 건수:")
                print(df['company_name'].value_counts().head(10))
                print(f"\n파일이 저장되었습니다.")
            else:
                print("수집된 데이터가 없습니다.")
        
        elif choice == "3":
            print("프로그램을 종료합니다.")
        else:
            print("잘못된 선택입니다.")
            
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")
        print(f"오류가 발생했습니다: {e}")
