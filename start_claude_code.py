"""
Claude Code Startup Launcher
Launches Claude Code with initial prompt and logs execution status.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import logging

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"claude_startup_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def launch_claude():
    """Launch Claude Code with initial prompt."""
    try:
        logger.info("🚀 Launching Claude Code")

        # Initial prompt for morning startup
        prompt = "Show me today's market news and any important updates for the options scanner"

        # Launch Claude Code in new terminal window
        # Using 'start' command to open in new window
        cmd = f'start cmd /k "cd /d {Path.cwd()} && claude \\"{prompt}\\""'

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            logger.info(f"✅ Claude Code launched successfully")
            logger.info(f"📝 Initial prompt: {prompt}")
        else:
            logger.error(f"❌ Claude Code failed with exit code {result.returncode}")
            if result.stderr:
                logger.error(f"STDERR: {result.stderr}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"💥 Exception during launch: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("CLAUDE CODE STARTUP LAUNCHER")
    logger.info("=" * 70)
    launch_claude()
