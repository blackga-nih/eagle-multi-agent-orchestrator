#!/usr/bin/env python3
"""
Generate placeholder banner images for Obsidian AI Agent Knowledge Base.
Uses GB Automation theme colors.

Usage:
    python create_banners.py --output-dir "/path/to/obsidian/AI-Agent-KB/_assets/banners"
"""

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is required. Install with: pip install pillow")
    exit(1)

# GB Automation Theme Colors
THEME = {
    "bg_primary": "#F3F1E7",
    "bg_panel": "#E6E4D9",
    "text_main": "#191919",
    "text_secondary": "#5C5C5C",
    "text_muted": "#8C8A84",
    "border": "#D6D4C8",
    "accent": "#D97757",
    "accent_deep": "#C26D52",
    "white": "#FFFFFF",
}

# Banner configurations
BANNERS = {
    "adw-banner": {
        "bg": THEME["accent"],
        "text": THEME["white"],
        "title": "ADWs",
        "subtitle": "AI Developer Workflows",
        "icon": ">>>"
    },
    "agent-banner": {
        "bg": THEME["accent_deep"],
        "text": THEME["white"],
        "title": "Agents",
        "subtitle": "Agent Definitions",
        "icon": "[A]"
    },
    "skill-banner": {
        "bg": THEME["text_main"],
        "text": THEME["bg_primary"],
        "title": "Skills",
        "subtitle": "Reusable Capabilities",
        "icon": "{*}"
    },
    "mcp-banner": {
        "bg": THEME["text_secondary"],
        "text": THEME["white"],
        "title": "MCP Servers",
        "subtitle": "External Connections",
        "icon": "<->"
    },
    "prompt-banner": {
        "bg": THEME["bg_panel"],
        "text": THEME["text_main"],
        "title": "Prompts",
        "subtitle": "Prompt Templates",
        "icon": "..."
    },
    "script-banner": {
        "bg": THEME["text_muted"],
        "text": THEME["white"],
        "title": "Scripts",
        "subtitle": "Code & Automation",
        "icon": "</>"
    },
    "expert-banner": {
        "bg": THEME["bg_primary"],
        "text": THEME["accent"],
        "title": "Experts",
        "subtitle": "Domain Expertise",
        "icon": "(!)",
        "border": THEME["accent"]
    },
    "dashboard-banner": {
        "bg": THEME["accent"],
        "text": THEME["white"],
        "title": "AI Agent KB",
        "subtitle": "Knowledge Base Dashboard",
        "icon": ":::",
        "gradient": True
    },
}


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def create_banner(name: str, config: dict, output_dir: Path, width: int = 800, height: int = 200):
    """Create a single banner image."""
    bg_color = hex_to_rgb(config["bg"])
    text_color = hex_to_rgb(config["text"])

    # Create image
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Add gradient effect for dashboard
    if config.get("gradient"):
        accent_deep = hex_to_rgb(THEME["accent_deep"])
        for x in range(width):
            ratio = x / width
            r = int(bg_color[0] * (1 - ratio) + accent_deep[0] * ratio)
            g = int(bg_color[1] * (1 - ratio) + accent_deep[1] * ratio)
            b = int(bg_color[2] * (1 - ratio) + accent_deep[2] * ratio)
            draw.line([(x, 0), (x, height)], fill=(r, g, b))

    # Add border for expert banner
    if config.get("border"):
        border_color = hex_to_rgb(config["border"])
        draw.rectangle([(0, 0), (width-1, height-1)], outline=border_color, width=3)

    # Try to load a nice font, fallback to default
    try:
        title_font = ImageFont.truetype("arial.ttf", 48)
        subtitle_font = ImageFont.truetype("arial.ttf", 20)
        icon_font = ImageFont.truetype("arial.ttf", 36)
    except:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        icon_font = ImageFont.load_default()

    # Draw icon (left side)
    icon_text = config.get("icon", "")
    draw.text((40, height // 2 - 18), icon_text, fill=text_color, font=icon_font)

    # Draw title (center)
    title = config["title"]
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_width) // 2, height // 2 - 40), title, fill=text_color, font=title_font)

    # Draw subtitle (center, below title)
    subtitle = config["subtitle"]
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((width - subtitle_width) // 2, height // 2 + 20), subtitle, fill=text_color, font=subtitle_font)

    # Save image
    output_path = output_dir / f"{name}.png"
    img.save(output_path, "PNG")
    print(f"Created: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate Obsidian banner images")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./banners",
        help="Output directory for banner images"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=800,
        help="Banner width in pixels"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=200,
        help="Banner height in pixels"
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating banners in: {output_dir}")
    print(f"Dimensions: {args.width}x{args.height}")
    print("-" * 40)

    for name, config in BANNERS.items():
        create_banner(name, config, output_dir, args.width, args.height)

    print("-" * 40)
    print(f"Generated {len(BANNERS)} banner images")


if __name__ == "__main__":
    main()
