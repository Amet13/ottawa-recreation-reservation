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
                f'❌ Failed to book a slot in {rec_name} '
                f'at {rec_slot["starting_time"]} '
                f'({rec_details["activity_button"]}), exception: {err}'
            )
            logging.error(message)
            self.telegram_bot.send_message(message)
            self.telegram_bot.send_photo(driver.get_screenshot_as_png())

    def _reserve_slot(self, driver: Any, rec_name: str,
                      rec_details: dict, rec_slot: dict) -> None:
        """
        Reserves slots in the given recreation facility.

        Args:
            driver (Any): WebDriver object for interacting with the browser.
            rec_name (str): Name of the recreation facility.
            rec_details (dict): Details of the recreation facility.
            rec_slot (dict): Details of the slot to be reserved.
        """
        logging.info(
            'Registering slot in %s at %s...',
            rec_name,
            rec_slot["starting_time"]
        )

        driver.get(rec_details["link"])
        driver.find_element(
            By.XPATH,
            "//div[text()='" + rec_details["activity_button"] + "']"
        ).click()

        reservation_count_input = driver.find_element(
            By.ID, "reservationCount"
        )
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
        driver.find_element(By.CLASS_NAME, "date-text").click()
        driver.find_element(
            By.XPATH,
            "//a[contains(span[@class='" +
            "mdc-button__label available-time'], '" +
            rec_slot["starting_time"] + "')]"
        ).click()
        time.sleep(random.uniform(0, 1))

        telephone_input = driver.find_element(By.ID, "telephone")
        email_input = driver.find_element(By.ID, "email")
        name_input = driver.find_element(
            By.XPATH, "//input[starts-with(@id, 'field')]"
        )

        telephone_input.clear()
        email_input.clear()
        name_input.clear()

        telephone_input.send_keys(self.env_var.phone_number)
        email_input.send_keys(self.env_var.imap_email)
        name_input.send_keys(self.env_var.name)
        time.sleep(random.uniform(0, 1))

        driver.find_element(By.CLASS_NAME, "mdc-button__ripple").click()

        self._perform_retry(driver)

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

        message: str = (
            f'✅ Successfully booked a slot in {rec_name} '
            f'at {rec_slot["starting_time"]} '
            f'({rec_details["activity_button"]})'
        )
        logging.info(message)
        self.telegram_bot.send_message(message)
        self.telegram_bot.send_photo(driver.get_screenshot_as_png())

    @staticmethod
    def _perform_retry(driver: Any) -> None:
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
                    time.sleep(random.uniform(2, 3))
                else:
                    break
            except NoSuchElementException:
                break

        if retries == MAX_RETRIES:
            raise Exception
