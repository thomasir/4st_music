"""
utility.py — v5.0
/info, name history, common chats
/genname — fancy Unicode fonts
/gendp   — generate profile picture
/couples — random user pairing
"""

import random
import io
import time
import asyncio
import logging
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from database import (
    register_user, get_name_history, get_common_chats_count,
    get_user_info, is_gbanned
)

log = logging.getLogger("ApexBot.utility")


# ══════════════════════════════════════════════════════════════════
# FANCY FONT MAPS
# ══════════════════════════════════════════════════════════════════

FONTS = {
    "Bold Serif":      "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
    "Italic Serif":    "𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧",
    "Script":          "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹𝑒𝒻𝑔𝒽𝒾𝒿𝓀𝓁𝓂𝓃𝑜𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
    "Bold Script":     "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃",
    "Fraktur":         "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷",
    "Double Struck":   "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫",
    "Monospace":       "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣",
    "Sans Bold":       "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇",
    "Sans Italic":     "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻",
    "Small Caps":      "ᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾQᴿˢᵀᵁᵛᵂˣʸᶻᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖqʳˢᵗᵘᵛʷˣʸᶻ",
}

NORMAL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# Decorative borders & symbols
DECORATIONS = [
    ("✨", "✨", "─────────────────"),
    ("🌟", "🌟", "═════════════════"),
    ("💫", "💫", "▬▬▬▬▬▬▬▬▬▬▬▬▬"),
    ("🔥", "🔥", "━━━━━━━━━━━━━━━"),
    ("⚡", "⚡", "▪▪▪▪▪▪▪▪▪▪▪▪▪▪"),
]

BORDER_STYLES = [
    "╔═══════════════╗\n║  {name}  ║\n╚═══════════════╝",
    "┌─────────────────┐\n│   {name}   │\n└─────────────────┘",
    "◆━━━━━━━━━━━━━━━━◆\n  {name}\n◆━━━━━━━━━━━━━━━━◆",
    "⊱━━━━━━━━━━━━━━━━⊰\n    {name}\n⊱━━━━━━━━━━━━━━━━⊰",
    "【 {name} 】",
]


def _convert_font(text: str, font_chars: str) -> str:
    result = []
    for ch in text:
        if ch.upper() in NORMAL:
            idx = NORMAL.index(ch.upper())
            try:
                if ch.isupper():
                    result.append(font_chars[idx])
                else:
                    result.append(font_chars[idx + 26])
            except IndexError:
                result.append(ch)
        else:
            result.append(ch)
    return "".join(result)


def _make_fancy_names(name: str) -> str:
    """Generate multiple fancy font versions of a name."""
    lines = [f"✨ **Fancy Fonts — {name}**\n"]
    for font_name, chars in FONTS.items():
        converted = _convert_font(name, chars)
        deco = random.choice(DECORATIONS)
        lines.append(
            f"**{font_name}:**\n"
            f"{deco[0]} {converted} {deco[1]}"
        )
    return "\n\n".join(lines)


# ── /genname ──────────────────────────────────────────────────────

@Client.on_message(filters.command(["genname", "fname", "fancyname"]))
async def genname_cmd(client: Client, message: Message):
    args = " ".join(message.command[1:]).strip()
    if not args:
        if message.from_user:
            args = message.from_user.first_name
        else:
            return await message.reply("❌ Name dein: `/genname YourName`")

    msg = await message.reply("✨ Generating fancy fonts...")
    text = _make_fancy_names(args)
    await msg.edit(text[:4000])


# ── /gendp — Generate DP image ────────────────────────────────────

DP_COLORS = [
    ("#1a1a2e", "#e94560"),  # Dark blue + red
    ("#0f3460", "#533483"),  # Navy + purple
    ("#16213e", "#0f3460"),  # Dark navy
    ("#1a1a1a", "#bb86fc"),  # Dark + violet
    ("#2d1b69", "#ff6b6b"),  # Dark purple + coral
    ("#0d2137", "#00b4d8"),  # Dark + cyan
    ("#1e3a5f", "#f39c12"),  # Dark blue + gold
    ("#2c1810", "#e67e22"),  # Dark brown + orange
]

DP_THEMES = {
    "default": ("👤", "#1a1a2e", "#e94560"),
    "birthday": ("🎂", "#1a1a2e", "#f39c12"),
    "couple": ("💑", "#2d1b69", "#ff6b6b"),
}


def _generate_dp_bytes(name: str, emoji: str = "👤", bg1: str = "#1a1a2e", accent: str = "#e94560") -> bytes:
    """Generate a simple colored DP image using PIL."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import math

        W, H = 512, 512
        img = Image.new("RGB", (W, H), bg1)
        draw = ImageDraw.Draw(img)

        # Background gradient simulation (concentric circles)
        for r in range(250, 0, -2):
            alpha = int(255 * (1 - r / 250))
            color = accent
            draw.ellipse([W//2-r, H//2-r, W//2+r, H//2+r], outline=color)

        # Central circle
        margin = 60
        draw.ellipse([margin, margin, W-margin, H-margin], fill=accent)
        inner_margin = 80
        draw.ellipse([inner_margin, inner_margin, W-inner_margin, H-inner_margin], fill=bg1)

        # Draw initials
        initials = ""
        for word in name.split():
            if word:
                initials += word[0].upper()
            if len(initials) >= 2:
                break
        if not initials:
            initials = name[:2].upper() if name else "?"

        # Try to use a font, fallback to default
        try:
            font_size = 160 if len(initials) == 1 else 100
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

        # Draw text centered
        if font:
            bbox = draw.textbbox((0, 0), initials, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (W - tw) // 2
            ty = (H - th) // 2 - 10
            draw.text((tx, ty), initials, fill="white", font=font)
        else:
            draw.text((W//2 - 30, H//2 - 20), initials, fill="white")

        # Draw name at bottom
        try:
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except Exception:
            small_font = None

        name_short = name[:15]
        if small_font:
            bbox2 = draw.textbbox((0, 0), name_short, font=small_font)
            tw2 = bbox2[2] - bbox2[0]
            draw.text(((W - tw2) // 2, H - 90), name_short, fill=accent, font=small_font)

        buf = io.BytesIO()
        img.save(buf, format="PNG", quality=95)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        log.error(f"gendp error: {e}")
        return None


@Client.on_message(filters.command(["gendp", "dp", "genpic"]))
async def gendp_cmd(client: Client, message: Message):
    args = message.command[1:]
    theme = "default"
    name  = ""

    if args:
        if args[0].lower() in ("birthday", "bday"):
            theme = "birthday"
            name = " ".join(args[1:])
        elif args[0].lower() in ("couple", "love"):
            theme = "couple"
            name = " ".join(args[1:])
        else:
            name = " ".join(args)

    if not name:
        if message.from_user:
            name = message.from_user.first_name
        else:
            return await message.reply("❌ `/gendp YourName`\n`/gendp birthday Name`\n`/gendp couple Name1 & Name2`")

    msg = await message.reply("🎨 DP generate ho raha hai...")

    emoji, bg1, accent = DP_THEMES.get(theme, DP_THEMES["default"])
    if theme == "default":
        bg1, accent = random.choice(DP_COLORS)

    img_bytes = _generate_dp_bytes(name, emoji, bg1, accent)
    if not img_bytes:
        return await msg.edit("❌ DP generate nahi ho saka! PIL install hai?")

    buf = io.BytesIO(img_bytes)
    buf.name = "dp.png"
    await msg.delete()

    caption = (
        f"🎨 **Generated DP**\n\n"
        f"👤 Name: **{name}**\n"
        f"🎭 Theme: {theme.title()}\n\n"
        f"_Apex Bot DP Generator_"
    )
    if theme == "birthday":
        caption = f"🎂 **Birthday DP — {name}**\n\n_Happy Birthday! 🎉_\n\n_Apex Bot DP Generator_"
    elif theme == "couple":
        caption = f"💑 **Couple DP — {name}**\n\n_❤️ Made with love_\n\n_Apex Bot DP Generator_"

    await message.reply_photo(photo=buf, caption=caption)


# ── /couples ──────────────────────────────────────────────────────

@Client.on_message(filters.command(["couples", "couple", "ship"]) & filters.group)
async def couples_cmd(client: Client, message: Message):
    msg = await message.reply("💑 Jodian bana raha hun...")

    members = []
    try:
        async for m in client.get_chat_members(message.chat.id):
            if not m.user.is_bot and not m.user.is_deleted:
                members.append(m.user)
    except Exception as e:
        return await msg.edit(f"❌ Members load nahi ho sake: {e}")

    if len(members) < 2:
        return await msg.edit("❌ Jodi banane ke liye kam se kam 2 members chahiye!")

    random.shuffle(members)
    couples = []
    for i in range(0, min(len(members) - 1, 10), 2):
        u1 = members[i]
        u2 = members[i + 1]
        compat = random.randint(50, 100)
        hearts = "❤️" * (compat // 20)
        couples.append(f"💑 **{u1.first_name}** + **{u2.first_name}** — {compat}% {hearts}")

    text = f"💘 **Today's Couples — {message.chat.title}**\n\n"
    text += "\n".join(couples)
    text += "\n\n_Kal dobara try karo naye couples ke liye! 😄_"

    await msg.edit(text)


# ── /info ──────────────────────────────────────────────────────────

@Client.on_message(filters.command(["info", "whois"]))
async def info_cmd(client: Client, message: Message):
    user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    if not user:
        return

    # Try to register/update user
    try:
        await register_user(user.id, user.username or "", user.first_name or "")
    except Exception:
        pass

    # Name history
    history = await get_name_history(user.id)
    common_chats = await get_common_chats_count(user.id)
    gban_info = await is_gbanned(user.id)
    db_info = await get_user_info(user.id)

    # Format first seen
    first_seen_text = "Unknown"
    if db_info and db_info.get("first_seen"):
        try:
            dt = datetime.fromtimestamp(db_info["first_seen"])
            first_seen_text = dt.strftime("%d %b %Y")
        except Exception:
            pass

    # Name history text
    name_hist_text = ""
    if history:
        shown = history[:5]
        names_list = []
        for name, ts in shown:
            try:
                dt = datetime.fromtimestamp(ts).strftime("%d %b %Y")
                names_list.append(f"  • {name} _({dt})_")
            except Exception:
                names_list.append(f"  • {name}")
        name_hist_text = (
            f"\n\n📝 **Name History** ({len(history)} changes):\n"
            + "\n".join(names_list)
        )
        if len(history) > 5:
            name_hist_text += f"\n  _...aur {len(history)-5} pehle_"

    gban_text = ""
    if gban_info:
        gban_text = f"\n🔨 **GBanned:** Yes _{gban_info['reason']}_"

    await message.reply(
        f"👤 **User Info**\n\n"
        f"🏷 Name     : {user.mention}\n"
        f"🆔 ID       : `{user.id}`\n"
        f"📛 Username : @{user.username or 'None'}\n"
        f"🔗 Link     : [Profile](tg://user?id={user.id})\n"
        f"🤖 Bot      : {'Yes' if user.is_bot else 'No'}\n"
        f"📅 First seen: {first_seen_text}\n"
        f"💬 Common GCs: `{common_chats}`"
        f"{gban_text}"
        f"{name_hist_text}",
        disable_web_page_preview=True,
    )
