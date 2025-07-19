"""
Main entry point for the Telegram bot.
"""

from telegram_bot.bot import TelegramBot


def main():
    """Main function to run the telegram bot."""
    try:
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        print(f"Error starting bot: {e}")
        raise


if __name__ == "__main__":
    main()
