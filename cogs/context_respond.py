import re
import time
from typing import Dict, Any

import discord
from discord.ext import commands

# Simple mapping: key -> config
# Edit this dict to add words/phrases and desired behavior.
# Keys may be plain words or phrases; set regex=True to use the key as a regex.
DEFAULT_RESPONDERS: Dict[str, Dict[str, Any]] = {
    "spamword": {"action": "delete", "message": "Please don't post spam.", "regex": False},
    "politics": {"action": "reply", "message": "Let's keep politics out of this channel.", "regex": False},
    r"(?i)\bhelicopter\b": {"action": "warn", "message": "That term isn't allowed here.", "regex": True},
    r"(?i)\b(climate change|global warming)\b": {"action": "reply", "message": "Please discuss policy respectfully.", "regex": True},
    r"(?i)\bnhs sucks\b": {"action": "warn", "message": "Wow wow wow... says who? If you don't like nhs, why are you even here?", "regex": True},
}


class ContextualResponder(commands.Cog):
    """Respond differently based on matched words/phrases."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Try to load from bot.settings if you added a mapping there; otherwise use default.
        self.responders = getattr(getattr(bot, "settings", None), "responders", DEFAULT_RESPONDERS)
        # cooldowns to avoid double-posting: (guild_id, pattern) -> last_ts
        self._cooldowns: Dict[tuple, float] = {}
        self.cooldown_seconds = 8.0

    def _match(self, content: str, key: str, cfg: Dict[str, Any]) -> bool:
        if cfg.get("regex", False):
            try:
                return bool(re.search(key, content))
            except re.error:
                return False
        # word-boundary match for plain phrase/word
        pattern = rf"\b{re.escape(key)}\b"
        return bool(re.search(pattern, content, flags=re.IGNORECASE))

    async def _perform_action(self, message: discord.Message, cfg: Dict[str, Any], user_id: str | None) -> None:
        action = cfg.get("action", "reply")
        reply_text = cfg.get("message")
        # delete if possible
        if action == "delete":
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            if reply_text:
                try:
                    await message.channel.send(f'<@{user_id}> {reply_text}' if user_id else reply_text)
                except discord.Forbidden:
                    pass
            return

        if action == "reply":
            try:
                await  message.channel.send(f'<@{user_id}> {reply_text}' if user_id else reply_text or "")
            except discord.Forbidden:
                pass
            return

        if action == "dm":
            try:
                await message.channel.send(f'<@{user_id}> {reply_text}' if user_id else reply_text or "")
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        if action == "warn":
            # a warn behaves like reply but could also log to mod channel
            try:
                await message.channel.send(f"{message.author.mention} {reply_text or 'Please follow the rules.'}")
            except discord.Forbidden:
                pass
            return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return
        user_id = message.author.id
        content = message.content or ""
        content_stripped = content.strip()
        if not content_stripped:
            return

        guild_id = message.guild.id if message.guild else 0

        for key, cfg in self.responders.items():
            if not key:
                continue
            # cheap cooldown per pattern per guild
            cd_key = (guild_id, key)
            last = self._cooldowns.get(cd_key, 0.0)
            now = time.time()
            if now - last < self.cooldown_seconds:
                continue

            if self._match(content, key, cfg):
                # update cooldown and act
                self._cooldowns[cd_key] = now
                await self._perform_action(message, cfg, user_id)
                # stop after first match; remove this `break` if you want multiple matches handled
                break

    # Optional admin commands to list/edit mapping at runtime (owner-only for simplicity)
    @commands.command(name="responders_list")
    @commands.is_owner()
    async def responders_list(self, ctx: commands.Context) -> None:
        lines = [f"{k} -> {v.get('action')}: {v.get('message','')}" for k, v in self.responders.items()]
        await ctx.send("Responders:\n" + ("\n".join(lines) if lines else "none"))

    @commands.command(name="responders_reload")
    @commands.is_owner()
    async def responders_reload(self, ctx: commands.Context) -> None:
        # If you persist responders to file or settings, reload here.
        self.responders = getattr(getattr(self.bot, "settings", None), "responders", DEFAULT_RESPONDERS)
        await ctx.send("Responders reloaded.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ContextualResponder(bot))
