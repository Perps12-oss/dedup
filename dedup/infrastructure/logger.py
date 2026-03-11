"""
DEDUP Logger - Structured logging for debugging and auditing.

Provides both console and file logging with structured output.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Logger:
    """
    Structured logger for DEDUP.
    
    Logs to both console and file with JSON formatting for machine parsing.
    """
    
    def __init__(
        self,
        name: str = "dedup",
        log_dir: Optional[Path] = None,
        console_level: LogLevel = LogLevel.INFO,
        file_level: LogLevel = LogLevel.DEBUG,
    ):
        self.name = name
        self.log_dir = log_dir or self._default_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.console_level = console_level
        self.file_level = file_level
        
        self._lock = threading.Lock()
        self._file_handle = None
        self._open_log_file()
    
    def _default_log_dir(self) -> Path:
        """Get default log directory."""
        if sys.platform == 'win32':
            log_dir = Path.home() / 'AppData' / 'Local' / 'dedup' / 'logs'
        elif sys.platform == 'darwin':
            log_dir = Path.home() / 'Library' / 'Logs' / 'dedup'
        else:
            log_dir = Path.home() / '.local' / 'share' / 'dedup' / 'logs'
        return log_dir
    
    def _open_log_file(self):
        """Open the log file for writing."""
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = self.log_dir / f"{self.name}_{timestamp}.log"
        
        try:
            self._file_handle = open(log_file, 'a', encoding='utf-8')
        except IOError:
            self._file_handle = None
    
    def _should_log(self, level: LogLevel, min_level: LogLevel) -> bool:
        """Check if a message should be logged at the given level."""
        levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return levels.index(level) >= levels.index(min_level)
    
    def _format_console(self, level: LogLevel, message: str, **kwargs) -> str:
        """Format message for console output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_str = level.value.upper()
        
        if kwargs:
            extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"[{timestamp}] {level_str}: {message} | {extra}"
        return f"[{timestamp}] {level_str}: {message}"
    
    def _format_json(self, level: LogLevel, message: str, **kwargs) -> str:
        """Format message as JSON for file output."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "logger": self.name,
            "message": message,
        }
        if kwargs:
            data["extra"] = kwargs
        return json.dumps(data, default=str)
    
    def _log(self, level: LogLevel, message: str, **kwargs):
        """Internal logging method."""
        with self._lock:
            # Console output
            if self._should_log(level, self.console_level):
                console_msg = self._format_console(level, message, **kwargs)
                if level in (LogLevel.ERROR, LogLevel.CRITICAL):
                    print(console_msg, file=sys.stderr)
                else:
                    print(console_msg)
            
            # File output
            if self._should_log(level, self.file_level) and self._file_handle:
                json_msg = self._format_json(level, message, **kwargs)
                try:
                    self._file_handle.write(json_msg + "\n")
                    self._file_handle.flush()
                except IOError:
                    pass
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self._log(LogLevel.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self._log(LogLevel.CRITICAL, message, **kwargs)
    
    def close(self):
        """Close the log file."""
        with self._lock:
            if self._file_handle:
                try:
                    self._file_handle.close()
                except IOError:
                    pass
                self._file_handle = None


# Global logger instance
_logger: Optional[Logger] = None
_logger_lock = threading.Lock()


def get_logger(
    name: str = "dedup",
    log_dir: Optional[Path] = None,
    console_level: LogLevel = LogLevel.INFO,
    file_level: LogLevel = LogLevel.DEBUG,
) -> Logger:
    """Get or create the global logger."""
    global _logger
    
    with _logger_lock:
        if _logger is None:
            _logger = Logger(name, log_dir, console_level, file_level)
        return _logger


def set_logger(logger: Logger):
    """Set the global logger."""
    global _logger
    with _logger_lock:
        _logger = logger
