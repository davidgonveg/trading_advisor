import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.getcwd())

from alerts.telegram import TelegramBot

def send_report():
    report_path = "backtesting/results/data_science_diagnosis.md"
    
    if not os.path.exists(report_path):
        print(f"Error: Report not found at {report_path}")
        return

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading report: {e}")
        return

    bot = TelegramBot()
    if not bot.enabled:
        print("Telegram bot is not enabled (missing credentials).")
        return

    # Telegram Message Limit is 4096. To be safe, we split at 3500 to keep markdown integrity better.
    # A simple split by structure (headers) is better than character count.
    
    # 1. Send Header
    bot.send_message("📊 **Nuevo Informe de Data Science Generado**")
    
    # 2. Split and Send
    # Strategy: Split by major headers "## "
    sections = content.split("\n## ")
    
    # First chunk might not start with ##
    if sections:
        # Re-attach the '## ' effectively
        # The first element is the Title block
        first_block = sections[0]
        bot.send_message(first_block)
        time.sleep(1) # Rate limit protection
        
        for section in sections[1:]:
            # Use '## ' to reconstruct header
            msg_chunk = "## " + section
            
            # Check length, if massive, split again? 
            # Assuming sections roughly fit. If analysis is huge, might fail.
            # Safety checks:
            if len(msg_chunk) > 4000:
                # Naive split
                parts = [msg_chunk[i:i+4000] for i in range(0, len(msg_chunk), 4000)]
                for p in parts:
                    bot.send_message(p)
                    time.sleep(1)
            else:
                bot.send_message(msg_chunk)
                time.sleep(1)
                
    print("Report sent to Telegram successfully.")

if __name__ == "__main__":
    send_report()
