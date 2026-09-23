#!/usr/bin/env python3
"""
Download a Telegram document through MTProto for GitHub Actions.

This bypasses the Telegram Public Bot API getFile 20MB download ceiling.
The bot account is authenticated with the same bot token, but the transfer
itself uses Telegram's MTProto file API.
"""
import asyncio
import os
import sys
from pathlib import Path

from telethon import TelegramClient


MAX_BYTES = 2 * 1024 * 1024 * 1024


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"GitHub Secret/variable {name} belum diatur. "
            f"Tambahkan {name} ke Settings > Secrets and variables > Actions."
        )
    return value


async def main() -> None:
    api_id = int(env_required("TELEGRAM_API_ID"))
    api_hash = env_required("TELEGRAM_API_HASH")
    bot_token = env_required("TELEGRAM_BOT_TOKEN")
    chat_id = int(env_required("TELEGRAM_SOURCE_CHAT_ID"))
    message_id = int(env_required("TELEGRAM_SOURCE_MESSAGE_ID"))
    output = Path(os.environ.get("TELEGRAM_OUTPUT", "work/project.zip"))

    output.parent.mkdir(parents=True, exist_ok=True)

    # Session is disposable and lives only on the ephemeral GitHub runner.
    session_path = str(Path("telegram-mtproto-session"))
    client = TelegramClient(
        session_path,
        api_id,
        api_hash,
        request_retries=8,
        connection_retries=8,
        retry_delay=2,
        auto_reconnect=True,
    )

    try:
        print(f"[Telegram] Connecting via MTProto (chat={chat_id}, message={message_id})")
        await client.start(bot_token=bot_token)

        message = await client.get_messages(chat_id, ids=message_id)
        if not message or not message.file:
            raise RuntimeError(
                "Pesan Telegram source tidak ditemukan atau tidak berisi file."
            )

        file_size = int(message.file.size or 0)
        file_name = message.file.name or "project.zip"
        print(f"[Telegram] Source: {file_name} ({file_size / 1024 / 1024:.2f} MB)")

        if file_size <= 0:
            raise RuntimeError("Ukuran file Telegram tidak valid.")
        if file_size > MAX_BYTES:
            raise RuntimeError(
                f"File melebihi batas 2GB ({file_size / 1024 / 1024:.2f} MB)."
            )
        if not file_name.lower().endswith(".zip"):
            raise RuntimeError("Source build harus berupa file .zip.")

        last_percent = -1

        def progress(current: int, total: int) -> None:
            nonlocal last_percent
            if not total:
                return
            percent = int(current * 100 / total)
            if percent != last_percent and (percent % 5 == 0 or percent == 100):
                last_percent = percent
                print(
                    f"[Telegram] Download {percent}% "
                    f"({current / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB)",
                    flush=True,
                )

        print("[Telegram] Downloading ZIP through MTProto...")
        downloaded = await client.download_media(
            message,
            file=str(output),
            progress_callback=progress,
        )
        if not downloaded or not output.exists():
            raise RuntimeError("Download Telegram selesai tetapi file output tidak ditemukan.")

        actual_size = output.stat().st_size
        if actual_size != file_size:
            raise RuntimeError(
                f"Ukuran file tidak cocok: Telegram={file_size}, output={actual_size}."
            )

        if actual_size > MAX_BYTES:
            raise RuntimeError("Output melebihi batas 2GB.")

        print(
            f"[Telegram] Download selesai: {output} "
            f"({actual_size / 1024 / 1024:.2f} MB)",
            flush=True,
        )
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"::error::{exc}", file=sys.stderr)
        raise
