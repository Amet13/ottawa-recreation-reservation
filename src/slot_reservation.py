import calendar
import logging
import time
import random
from typing import Any
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from confirmation_code_extractor import ConfirmationCodeExtractor
from telegram_bot import TelegramBot
from env_vars import EnvVars
from constant import GROUP_SIZE, MAX_RETRIES


class SlotReservation:
    """
    A class that handles the reservation of slots in a recreation facility.

    Attributes:
    - env_var (EnvVars): An instance of the EnvVars class containing env vars.
    - telegram_bot (TelegramBot): An instance of the TelegramBot class
        for sending messages and photos.

    Methods:
    - reserve_slots(driver, rec_name, rec_details, rec_slot):
        Reserves slots in the given recreation facility.
    - _reserve_slot(driver, rec_name, rec_details, rec_slot):
        Helper method that performs the actual slot reservation.
    - _fill_reservation_form(driver):
        Fills the reservation form with user details.
    - _perform_retry(driver):
        Performs the retry logic for slot reservation.
    """

    def __init__(self) -> None:
        """
        Initializes a SlotReservation object.

        Initializes environment variables and Telegram bot.
        """
        env_vars = EnvVars.check_env_vars(EnvVars.REQUIRED_VARS)
        self.env_var: EnvVars = EnvVars(env_vars)
        self.telegram_bot: TelegramBot = TelegramBot(self.env_var)

    def reserve_slots(self, driver: Any, rec_name: str,
                      rec_details: dict, rec_slot: dict) -> None:
        """
        Reserves slots in the given recreation facility.

        Args:
            driver (Any): WebDriver object for interacting with the browser.
            rec_name (str): Name of the recreation facility.
            rec_details (dict): Details of the recreation facility.
            rec_slot (dict): Details of the slot to be reserved.
        """
        try:
            self._reserve_slot(driver, rec_name, rec_details, rec_slot)
        except NoSuchElementException as err:
            message: str = (
                f'❌ Failed to reserve a slot in {rec_name} '
                f'at {rec_slot["starting_time"]} '
                f'({rec_details["activity_button"]}), exception: {err}'
            )
            logging.error(message)
            self.telegram_bot.send_message(message)
            self.telegram_bot.send_photo(driver.get_screenshot_as_png())

    def _reserve_slot(self, driver: Any, rec_name: str,
                      rec_details: dict, rec_slot: dict) -> bool:
        """
        Reserves slots in the given recreation facility.

        Args:
            driver (Any): WebDriver object for interacting with the browser.
            rec_name (str): Name of the recreation facility.
            rec_details (dict): Details of the recreation facility.
            rec_slot (dict): Details of the slot to be reserved.
        """
        logging.info(
            'Reserving slot in %s at %s...',
            rec_name, rec_slot["starting_time"]
        )

        driver.get(rec_details["link"])
        driver.find_element(
            By.XPATH,
            "//div[text()='" + rec_details["activity_button"] + "']"
        ).click()

        try:
            reservation_count_input = driver.find_element(
                By.ID, "reservationCount"
            )
        except NoSuchElementException:
            driver.find_element(
                By.XPATH, "//form[contains(@action, 'NoAvailableTime')]"
            )
            message: str = (
                f'❌ No more available times in {rec_name} at '
                f'{rec_slot["starting_time"]} '
                f'({rec_details["activity_button"]})'
            )
            logging.error(message)
            self.telegram_bot.send_message(message)
            self.telegram_bot.send_photo(driver.get_screenshot_as_png())
            return False

        # When page doesn't have dialogue 'How many people in your group?'
        if reservation_count_input.get_attribute("type") == "hidden":
            message: str = (
                f'❌ No slots available in {rec_name} at '
                f'{rec_slot["starting_time"]} '
                f'({rec_details["activity_button"]})'
            )
            logging.error(message)
            self.telegram_bot.send_message(message)
            self.telegram_bot.send_photo(driver.get_screenshot_as_png())
            return False

        reservation_count_input.clear()
        reservation_count_input.send_keys(GROUP_SIZE)
        driver.find_element(By.CLASS_NAME, "mdc-button__ripple").click()
        driver.find_elements(By.CLASS_NAME, "header-text")[-1].click()
        weekday_name = calendar.day_name[rec_slot["day_of_week"]-1]

        driver.find_element(
            By.CSS_SELECTOR,
            "[aria-label*='" +
            rec_slot["starting_time"] + " " +
            weekday_name + "']"
        ).click()
        time.sleep(random.uniform(0.1, 0.9))

        self._fill_reservation_form(driver)

        if not self._perform_retry(driver):
            message: str = (
                f'❌ Failed to reserve slot in {rec_name} '
                f'at {rec_slot["starting_time"]} '
                f'({rec_details["activity_button"]}) '
                f'after {MAX_RETRIES} retries'
            )
            logging.error(message)
            self.telegram_bot.send_message(message)
            self.telegram_bot.send_photo(driver.get_screenshot_as_png())
            return False

        confirmation_code = None
        while confirmation_code is None:
            time.sleep(1)
            logging.info("Waiting for a code to verify reservation...")
            extractor = ConfirmationCodeExtractor(
                self.env_var.imap_server,
                self.env_var.imap_email,
                self.env_var.imap_password
            )
            confirmation_code = extractor.get_confirmation_code()

        logging.info('✅ Verification code is %s', confirmation_code)

        code_input = driver.find_element(By.ID, "code")
        code_input.clear()
        code_input.send_keys(confirmation_code)
        driver.find_element(By.CLASS_NAME, "mdc-button__ripple").click()

        try:
            driver.find_element(
                By.XPATH,
                "//*[text()='Time and number of participants']"
            )
            driver.find_elements(
                By.CLASS_NAME, "mdc-button__ripple"
            )[-1].click()
        except NoSuchElementException:
            logging.info("Skipping final confirmation page...")

        message: str = (
            f'✅ Successfully reserved a slot in {rec_name} '
            f'at {rec_slot["starting_time"]} '
            f'({rec_details["activity_button"]})'
        )
        logging.info(message)
        self.telegram_bot.send_message(message)
        self.telegram_bot.send_photo(driver.get_screenshot_as_png())

        return True

    def _fill_reservation_form(self, driver: Any) -> None:
        """
        Fills the reservation form with user details.

        Args:
            driver (Any): WebDriver object for interacting with the browser.
        """
        telephone_input = driver.find_element(By.ID, "telephone")
        telephone_input.clear()
        for symbol in self.env_var.phone_number:
            telephone_input.send_keys(symbol)
            time.sleep(random.uniform(0.01, 0.1))

        email_input = driver.find_element(By.ID, "email")
        email_input.clear()
        for symbol in self.env_var.imap_email:
            email_input.send_keys(symbol)
            time.sleep(random.uniform(0.01, 0.1))

        name_input = driver.find_element(
            By.XPATH, "//input[starts-with(@id, 'field')]"
        )
        name_input.clear()
        for symbol in self.env_var.name:
            name_input.send_keys(symbol)
            time.sleep(random.uniform(0.01, 0.1))

        driver.find_element(By.CLASS_NAME, "mdc-button__ripple").click()

    @staticmethod
    def _perform_retry(driver: Any) -> bool:
        """
        Performs the retry logic for slot reservation.

        Args:
            driver (Any): WebDriver object for interacting with the browser.
        """
        retries = 0
        while retries < MAX_RETRIES:
            try:
                retry_text_element = driver.find_element(
                    By.XPATH, "//span[text()='Retry']"
                )
                if retry_text_element.is_displayed():
                    retries += 1
                    logging.error("❌ Retry attempt %d", retries)
                    driver.find_element(
                        By.CLASS_NAME, "mdc-button__ripple"
                    ).click()
                    time.sleep(random.uniform(1, 3))
                else:
                    break
            except NoSuchElementException:
                break

        if retries == MAX_RETRIES:
            return False

        return True
