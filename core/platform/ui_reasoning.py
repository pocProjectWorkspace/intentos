"""IntentOS Industry-Aware UI Reasoning Engine (Phase 4.12).

Maps product types to UI patterns, color palettes, font pairings, and
complete design systems.  Inspired by UI/UX Pro Max.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


# ── Enums ─────────────────────────────────────────────────────────────


class ProductType(Enum):
    SAAS = "saas"
    MICRO_SAAS = "micro_saas"
    ECOMMERCE = "ecommerce"
    FINTECH = "fintech"
    HEALTHCARE = "healthcare"
    LEGAL = "legal"
    EDUCATION = "education"
    SECURITY_TOOL = "security_tool"
    AI_TOOL = "ai_tool"
    B2B_SERVICE = "b2b_service"
    CONSUMER_APP = "consumer_app"
    ENTERPRISE_ADMIN = "enterprise_admin"


# ── Data models ───────────────────────────────────────────────────────


@dataclass
class UIStyle:
    name: str
    css_keywords: List[str]
    effects: List[str]
    accessibility_grade: str  # "A" / "B" / "C"
    performance_notes: str


@dataclass
class ColorPalette:
    primary: str
    secondary: str
    accent: str
    cta: str
    background: str
    foreground: str
    card: str
    muted: str
    border: str
    destructive: str


@dataclass
class FontPairing:
    heading_font: str
    body_font: str
    mono_font: str
    google_fonts_url: str


@dataclass
class DesignSystem:
    product_type: ProductType
    style: UIStyle
    colors: ColorPalette
    fonts: FontPairing
    spacing_scale: Dict[str, str]
    shadow_scale: Dict[str, str]
    anti_patterns: List[str]
    checklist: List[str]


# ── Lookup tables ─────────────────────────────────────────────────────

_STYLES: Dict[ProductType, UIStyle] = {
    ProductType.SAAS: UIStyle(
        name="Clean SaaS",
        css_keywords=["clean", "minimal", "professional"],
        effects=["subtle-shadow", "smooth-transitions"],
        accessibility_grade="A",
        performance_notes="Optimise for fast first-paint; lazy-load dashboards.",
    ),
    ProductType.MICRO_SAAS: UIStyle(
        name="Compact Micro-SaaS",
        css_keywords=["compact", "focused", "lightweight"],
        effects=["micro-interactions"],
        accessibility_grade="B",
        performance_notes="Ship minimal CSS; inline critical styles.",
    ),
    ProductType.ECOMMERCE: UIStyle(
        name="Conversion-Driven",
        css_keywords=["vibrant", "conversion-focused", "scannable"],
        effects=["hover-zoom", "skeleton-loading", "carousel"],
        accessibility_grade="B",
        performance_notes="Image-heavy; use responsive images and CDN.",
    ),
    ProductType.FINTECH: UIStyle(
        name="Trust & Clarity",
        css_keywords=["clean", "trust-focused", "data-dense"],
        effects=["subtle-shadow", "number-animation"],
        accessibility_grade="A",
        performance_notes="Real-time data; optimise WebSocket rendering.",
    ),
    ProductType.HEALTHCARE: UIStyle(
        name="Accessible & Calm",
        css_keywords=["accessible", "calm", "high-contrast"],
        effects=["gentle-transitions"],
        accessibility_grade="A",
        performance_notes="Must work on low-bandwidth clinical networks.",
    ),
    ProductType.LEGAL: UIStyle(
        name="Formal & Structured",
        css_keywords=["formal", "structured", "readable"],
        effects=["subtle-borders"],
        accessibility_grade="A",
        performance_notes="Heavy text; use progressive rendering for long docs.",
    ),
    ProductType.EDUCATION: UIStyle(
        name="Friendly & Engaging",
        css_keywords=["friendly", "engaging", "colorful"],
        effects=["progress-animations", "confetti-on-complete"],
        accessibility_grade="A",
        performance_notes="Interactive content; lazy-load media.",
    ),
    ProductType.SECURITY_TOOL: UIStyle(
        name="Dark & Precise",
        css_keywords=["dark", "precise", "technical"],
        effects=["glow-accents", "terminal-style-text"],
        accessibility_grade="B",
        performance_notes="Log-heavy; virtualise long lists.",
    ),
    ProductType.AI_TOOL: UIStyle(
        name="Modern Dark AI",
        css_keywords=["modern", "dark", "futuristic"],
        effects=["gradient-glow", "typing-indicator", "streaming-text"],
        accessibility_grade="B",
        performance_notes="Streaming responses; handle partial DOM updates.",
    ),
    ProductType.B2B_SERVICE: UIStyle(
        name="Enterprise Friendly",
        css_keywords=["professional", "clean", "structured"],
        effects=["subtle-shadow", "smooth-transitions"],
        accessibility_grade="A",
        performance_notes="Dashboard-heavy; chunk large data tables.",
    ),
    ProductType.CONSUMER_APP: UIStyle(
        name="Bold & Playful",
        css_keywords=["bold", "playful", "mobile-first"],
        effects=["spring-animations", "haptic-feedback", "pull-to-refresh"],
        accessibility_grade="B",
        performance_notes="Mobile-first; target <3s LCP on 3G.",
    ),
    ProductType.ENTERPRISE_ADMIN: UIStyle(
        name="Dense & Efficient",
        css_keywords=["dense", "efficient", "neutral"],
        effects=["collapsible-panels", "inline-editing"],
        accessibility_grade="A",
        performance_notes="Complex forms; debounce saves, paginate tables.",
    ),
}

_COLORS: Dict[ProductType, ColorPalette] = {
    ProductType.SAAS: ColorPalette(
        primary="#4F46E5", secondary="#6B7280", accent="#F59E0B",
        cta="#4F46E5", background="#FFFFFF", foreground="#111827",
        card="#F9FAFB", muted="#9CA3AF", border="#E5E7EB",
        destructive="#EF4444",
    ),
    ProductType.MICRO_SAAS: ColorPalette(
        primary="#7C3AED", secondary="#6B7280", accent="#F59E0B",
        cta="#7C3AED", background="#FFFFFF", foreground="#111827",
        card="#F9FAFB", muted="#9CA3AF", border="#E5E7EB",
        destructive="#EF4444",
    ),
    ProductType.ECOMMERCE: ColorPalette(
        primary="#EA580C", secondary="#1E293B", accent="#FACC15",
        cta="#EA580C", background="#FFFFFF", foreground="#0F172A",
        card="#FFF7ED", muted="#94A3B8", border="#E2E8F0",
        destructive="#DC2626",
    ),
    ProductType.FINTECH: ColorPalette(
        primary="#1D4ED8", secondary="#1E3A5F", accent="#10B981",
        cta="#1D4ED8", background="#FFFFFF", foreground="#0F172A",
        card="#F0F4FF", muted="#94A3B8", border="#CBD5E1",
        destructive="#DC2626",
    ),
    ProductType.HEALTHCARE: ColorPalette(
        primary="#0D9488", secondary="#0F766E", accent="#06B6D4",
        cta="#0D9488", background="#FFFFFF", foreground="#134E4A",
        card="#F0FDFA", muted="#94A3B8", border="#CCFBF1",
        destructive="#DC2626",
    ),
    ProductType.LEGAL: ColorPalette(
        primary="#1E3A5F", secondary="#374151", accent="#D97706",
        cta="#1E3A5F", background="#FFFFFF", foreground="#111827",
        card="#F8FAFC", muted="#9CA3AF", border="#D1D5DB",
        destructive="#B91C1C",
    ),
    ProductType.EDUCATION: ColorPalette(
        primary="#2563EB", secondary="#7C3AED", accent="#F59E0B",
        cta="#2563EB", background="#FFFFFF", foreground="#1E293B",
        card="#EFF6FF", muted="#94A3B8", border="#BFDBFE",
        destructive="#EF4444",
    ),
    ProductType.SECURITY_TOOL: ColorPalette(
        primary="#3B82F6", secondary="#1E293B", accent="#22D3EE",
        cta="#3B82F6", background="#0F172A", foreground="#E2E8F0",
        card="#1E293B", muted="#64748B", border="#334155",
        destructive="#F87171",
    ),
    ProductType.AI_TOOL: ColorPalette(
        primary="#8B5CF6", secondary="#1E293B", accent="#22D3EE",
        cta="#8B5CF6", background="#0A0A0F", foreground="#E2E8F0",
        card="#18181B", muted="#71717A", border="#27272A",
        destructive="#F87171",
    ),
    ProductType.B2B_SERVICE: ColorPalette(
        primary="#2563EB", secondary="#475569", accent="#F59E0B",
        cta="#2563EB", background="#FFFFFF", foreground="#0F172A",
        card="#F8FAFC", muted="#94A3B8", border="#E2E8F0",
        destructive="#DC2626",
    ),
    ProductType.CONSUMER_APP: ColorPalette(
        primary="#EC4899", secondary="#8B5CF6", accent="#F59E0B",
        cta="#EC4899", background="#FFFFFF", foreground="#111827",
        card="#FDF2F8", muted="#9CA3AF", border="#FBCFE8",
        destructive="#EF4444",
    ),
    ProductType.ENTERPRISE_ADMIN: ColorPalette(
        primary="#475569", secondary="#64748B", accent="#3B82F6",
        cta="#3B82F6", background="#FFFFFF", foreground="#0F172A",
        card="#F8FAFC", muted="#94A3B8", border="#E2E8F0",
        destructive="#DC2626",
    ),
}

_FONTS: Dict[ProductType, FontPairing] = {
    ProductType.SAAS: FontPairing(
        heading_font="Inter",
        body_font="Inter",
        mono_font="JetBrains Mono",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;500",
    ),
    ProductType.MICRO_SAAS: FontPairing(
        heading_font="Inter",
        body_font="Inter",
        mono_font="Fira Code",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Fira+Code:wght@400",
    ),
    ProductType.ECOMMERCE: FontPairing(
        heading_font="DM Sans",
        body_font="DM Sans",
        mono_font="JetBrains Mono",
        google_fonts_url="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400",
    ),
    ProductType.FINTECH: FontPairing(
        heading_font="IBM Plex Sans",
        body_font="IBM Plex Sans",
        mono_font="IBM Plex Mono",
        google_fonts_url="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500",
    ),
    ProductType.HEALTHCARE: FontPairing(
        heading_font="Source Sans 3",
        body_font="Source Sans 3",
        mono_font="Source Code Pro",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Code+Pro:wght@400",
    ),
    ProductType.LEGAL: FontPairing(
        heading_font="Merriweather",
        body_font="Source Sans 3",
        mono_font="Source Code Pro",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=Source+Sans+3:wght@400;600&family=Source+Code+Pro:wght@400",
    ),
    ProductType.EDUCATION: FontPairing(
        heading_font="Nunito",
        body_font="Nunito",
        mono_font="Fira Code",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&family=Fira+Code:wght@400",
    ),
    ProductType.SECURITY_TOOL: FontPairing(
        heading_font="Space Grotesk",
        body_font="Inter",
        mono_font="Fira Code",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@400;500&family=Fira+Code:wght@400",
    ),
    ProductType.AI_TOOL: FontPairing(
        heading_font="Space Grotesk",
        body_font="Inter",
        mono_font="JetBrains Mono",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400",
    ),
    ProductType.B2B_SERVICE: FontPairing(
        heading_font="Inter",
        body_font="Inter",
        mono_font="JetBrains Mono",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400",
    ),
    ProductType.CONSUMER_APP: FontPairing(
        heading_font="Plus Jakarta Sans",
        body_font="Plus Jakarta Sans",
        mono_font="Fira Code",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;700&family=Fira+Code:wght@400",
    ),
    ProductType.ENTERPRISE_ADMIN: FontPairing(
        heading_font="Inter",
        body_font="Inter",
        mono_font="JetBrains Mono",
        google_fonts_url="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500",
    ),
}

_ANTI_PATTERNS: Dict[ProductType, List[str]] = {
    ProductType.SAAS: [
        "No feature overload on landing page",
        "No inconsistent navigation across sections",
        "Avoid complex onboarding without progressive disclosure",
    ],
    ProductType.MICRO_SAAS: [
        "No over-engineering the UI for a single-purpose tool",
        "Avoid unnecessary settings pages",
        "No heavy framework bundles for simple interfaces",
    ],
    ProductType.ECOMMERCE: [
        "No distracting animations on checkout flow",
        "Avoid hiding total price until last step",
        "No auto-playing video on product pages",
        "Avoid dark patterns in cart (pre-checked add-ons)",
    ],
    ProductType.FINTECH: [
        "No playful animations on transaction screens",
        "No bright colors on error states",
        "Avoid hiding fees or decimal precision",
        "No ambiguous confirmation dialogs for money movement",
    ],
    ProductType.HEALTHCARE: [
        "No low-contrast text on clinical data",
        "Avoid small tap targets for elderly users",
        "No gamification of medical information",
        "Avoid jargon without plain-language alternatives",
    ],
    ProductType.LEGAL: [
        "No decorative fonts in legal document displays",
        "Avoid truncating clause text without expand option",
        "No ambiguous action labels on contract signing",
    ],
    ProductType.EDUCATION: [
        "No overwhelming dashboards for young learners",
        "Avoid punishing failure animations",
        "No timed interactions without pause option",
    ],
    ProductType.SECURITY_TOOL: [
        "No hiding severity levels behind extra clicks",
        "Avoid using only color to indicate threat level",
        "No auto-dismissing critical alerts",
        "Avoid playful illustrations for serious vulnerabilities",
    ],
    ProductType.AI_TOOL: [
        "No fake typing delays to simulate intelligence",
        "Avoid hiding model confidence or sources",
        "No auto-executing generated code without confirmation",
    ],
    ProductType.B2B_SERVICE: [
        "No consumer-style gamification in enterprise context",
        "Avoid long wizard flows without save-and-resume",
        "No mandatory tours that block first use",
    ],
    ProductType.CONSUMER_APP: [
        "No infinite scroll without back-to-top",
        "Avoid notification spam on first install",
        "No dark patterns for subscription upgrades",
    ],
    ProductType.ENTERPRISE_ADMIN: [
        "No bulk-action buttons without confirmation",
        "Avoid hiding audit-relevant information",
        "No destructive actions with single click",
        "Avoid pagination without items-per-page option",
    ],
}

_BASE_CHECKLIST: List[str] = [
    "Contrast ratio >= 4.5:1 on all text",
    "Touch targets >= 44pt on mobile",
    "Focus indicators visible on all interactive elements",
    "Keyboard navigation works for all flows",
    "Screen reader announces dynamic content changes",
    "Loading states for all async operations",
    "Error messages are actionable and specific",
    "No horizontal scroll on mobile viewports",
]

_SPACING_SCALE: Dict[str, str] = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2rem",
    "2xl": "3rem",
    "3xl": "4rem",
}

_SHADOW_SCALE: Dict[str, str] = {
    "sm": "0 1px 2px rgba(0,0,0,0.05)",
    "md": "0 4px 6px rgba(0,0,0,0.07)",
    "lg": "0 10px 15px rgba(0,0,0,0.1)",
    "xl": "0 20px 25px rgba(0,0,0,0.1)",
}


# ── Engine ────────────────────────────────────────────────────────────


class UIReasoningEngine:
    """Maps product types to UI patterns, producing complete design systems."""

    # ── public API ────────────────────────────────────────────────────

    def get_style(self, product_type: ProductType) -> UIStyle:
        self._validate(product_type)
        return _STYLES.get(product_type, _STYLES[ProductType.SAAS])

    def get_colors(self, product_type: ProductType) -> ColorPalette:
        self._validate(product_type)
        return _COLORS.get(product_type, _COLORS[ProductType.SAAS])

    def get_fonts(self, product_type: ProductType) -> FontPairing:
        self._validate(product_type)
        return _FONTS.get(product_type, _FONTS[ProductType.SAAS])

    def generate_design_system(self, product_type: ProductType) -> DesignSystem:
        self._validate(product_type)
        return DesignSystem(
            product_type=product_type,
            style=self.get_style(product_type),
            colors=self.get_colors(product_type),
            fonts=self.get_fonts(product_type),
            spacing_scale=dict(_SPACING_SCALE),
            shadow_scale=dict(_SHADOW_SCALE),
            anti_patterns=list(
                _ANTI_PATTERNS.get(product_type, _ANTI_PATTERNS[ProductType.SAAS])
            ),
            checklist=list(_BASE_CHECKLIST),
        )

    def generate_css_variables(self, design_system: DesignSystem) -> str:
        """Return a CSS custom-properties string from a DesignSystem."""
        lines = [":root {"]

        # Colors
        c = design_system.colors
        for name in (
            "primary", "secondary", "accent", "cta", "background",
            "foreground", "card", "muted", "border", "destructive",
        ):
            lines.append(f"  --color-{name}: {getattr(c, name)};")

        # Fonts
        f = design_system.fonts
        lines.append(f"  --font-heading: '{f.heading_font}', sans-serif;")
        lines.append(f"  --font-body: '{f.body_font}', sans-serif;")
        lines.append(f"  --font-mono: '{f.mono_font}', monospace;")

        # Spacing
        for key, val in design_system.spacing_scale.items():
            lines.append(f"  --spacing-{key}: {val};")

        # Shadows
        for key, val in design_system.shadow_scale.items():
            lines.append(f"  --shadow-{key}: {val};")

        lines.append("}")
        return "\n".join(lines)

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    def _validate(product_type: ProductType) -> None:
        if product_type is None:
            raise TypeError("product_type must not be None")
        if not isinstance(product_type, ProductType):
            raise ValueError(
                f"Expected ProductType enum, got {type(product_type).__name__}"
            )
