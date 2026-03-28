"""Tests for IntentOS Industry-Aware UI Reasoning Engine (Phase 4.12)."""

import pytest

from core.platform.ui_reasoning import (
    ColorPalette,
    DesignSystem,
    FontPairing,
    ProductType,
    UIReasoningEngine,
    UIStyle,
)


@pytest.fixture
def engine():
    return UIReasoningEngine()


# ── ProductType enum ──────────────────────────────────────────────────

class TestProductType:
    def test_all_types_exist(self):
        expected = [
            "SAAS", "MICRO_SAAS", "ECOMMERCE", "FINTECH", "HEALTHCARE",
            "LEGAL", "EDUCATION", "SECURITY_TOOL", "AI_TOOL", "B2B_SERVICE",
            "CONSUMER_APP", "ENTERPRISE_ADMIN",
        ]
        for name in expected:
            assert hasattr(ProductType, name), f"Missing ProductType.{name}"

    def test_enum_values_are_strings(self):
        for member in ProductType:
            assert isinstance(member.value, str)


# ── UIStyle model ─────────────────────────────────────────────────────

class TestUIStyle:
    def test_fields(self):
        style = UIStyle(
            name="Test",
            css_keywords=["clean", "minimal"],
            effects=["shadow"],
            accessibility_grade="A",
            performance_notes="fast",
        )
        assert style.name == "Test"
        assert style.css_keywords == ["clean", "minimal"]
        assert style.effects == ["shadow"]
        assert style.accessibility_grade == "A"
        assert style.performance_notes == "fast"


# ── ColorPalette model ───────────────────────────────────────────────

class TestColorPalette:
    def test_all_color_slots(self):
        colors = ColorPalette(
            primary="#0066FF", secondary="#6B7280", accent="#F59E0B",
            cta="#10B981", background="#FFFFFF", foreground="#111827",
            card="#F9FAFB", muted="#9CA3AF", border="#E5E7EB",
            destructive="#EF4444",
        )
        assert colors.primary == "#0066FF"
        assert colors.destructive == "#EF4444"

    def test_hex_validation(self):
        """All color values must be valid hex strings."""
        colors = ColorPalette(
            primary="#0066FF", secondary="#6B7280", accent="#F59E0B",
            cta="#10B981", background="#FFFFFF", foreground="#111827",
            card="#F9FAFB", muted="#9CA3AF", border="#E5E7EB",
            destructive="#EF4444",
        )
        for field_name in [
            "primary", "secondary", "accent", "cta", "background",
            "foreground", "card", "muted", "border", "destructive",
        ]:
            val = getattr(colors, field_name)
            assert val.startswith("#"), f"{field_name} must start with #"
            assert len(val) in (4, 7), f"{field_name} hex length invalid"


# ── FontPairing model ────────────────────────────────────────────────

class TestFontPairing:
    def test_fields(self):
        fonts = FontPairing(
            heading_font="Inter",
            body_font="Inter",
            mono_font="JetBrains Mono",
            google_fonts_url="https://fonts.googleapis.com/css2?family=Inter",
        )
        assert fonts.heading_font == "Inter"
        assert fonts.mono_font == "JetBrains Mono"
        assert fonts.google_fonts_url.startswith("https://")

    def test_mono_font_always_present(self, engine):
        """Every product type must include a mono font."""
        for pt in ProductType:
            fonts = engine.get_fonts(pt)
            assert fonts.mono_font, f"Missing mono_font for {pt.name}"


# ── DesignSystem model ───────────────────────────────────────────────

class TestDesignSystem:
    def test_design_system_structure(self, engine):
        ds = engine.generate_design_system(ProductType.SAAS)
        assert isinstance(ds, DesignSystem)
        assert ds.product_type == ProductType.SAAS
        assert isinstance(ds.style, UIStyle)
        assert isinstance(ds.colors, ColorPalette)
        assert isinstance(ds.fonts, FontPairing)
        assert isinstance(ds.spacing_scale, dict)
        assert isinstance(ds.shadow_scale, dict)
        assert isinstance(ds.anti_patterns, list)
        assert isinstance(ds.checklist, list)


# ── UIReasoningEngine: get_style ──────────────────────────────────────

class TestGetStyle:
    def test_fintech_clean_trust(self, engine):
        style = engine.get_style(ProductType.FINTECH)
        assert isinstance(style, UIStyle)
        combined = " ".join(style.css_keywords).lower()
        assert "clean" in combined or "trust" in combined

    def test_healthcare_accessible(self, engine):
        style = engine.get_style(ProductType.HEALTHCARE)
        assert style.accessibility_grade == "A"
        combined = " ".join(style.css_keywords).lower()
        assert "accessible" in combined or "calm" in combined

    def test_ai_tool_modern(self, engine):
        style = engine.get_style(ProductType.AI_TOOL)
        combined = " ".join(style.css_keywords).lower()
        assert "modern" in combined or "dark" in combined

    def test_all_types_return_style(self, engine):
        for pt in ProductType:
            style = engine.get_style(pt)
            assert isinstance(style, UIStyle)


# ── UIReasoningEngine: get_colors ─────────────────────────────────────

class TestGetColors:
    def test_fintech_blue_primary(self, engine):
        colors = engine.get_colors(ProductType.FINTECH)
        assert isinstance(colors, ColorPalette)
        # Blue hue: hex starts with a high blue component
        r = int(colors.primary[1:3], 16)
        b = int(colors.primary[5:7], 16)
        assert b > r, "FINTECH primary should be blue-dominant"

    def test_healthcare_green_teal(self, engine):
        colors = engine.get_colors(ProductType.HEALTHCARE)
        g = int(colors.primary[3:5], 16)
        r = int(colors.primary[1:3], 16)
        assert g >= r, "HEALTHCARE primary should be green/teal-dominant"

    def test_security_tool_dark(self, engine):
        colors = engine.get_colors(ProductType.SECURITY_TOOL)
        bg_brightness = sum(
            int(colors.background[i:i+2], 16) for i in (1, 3, 5)
        )
        assert bg_brightness < 384, "SECURITY_TOOL background should be dark"

    def test_enterprise_admin_neutral(self, engine):
        colors = engine.get_colors(ProductType.ENTERPRISE_ADMIN)
        assert isinstance(colors, ColorPalette)
        # Neutral = relatively low saturation primary
        r = int(colors.primary[1:3], 16)
        g = int(colors.primary[3:5], 16)
        b = int(colors.primary[5:7], 16)
        spread = max(r, g, b) - min(r, g, b)
        assert spread < 180, "ENTERPRISE_ADMIN should use neutral/professional palette"


# ── UIReasoningEngine: get_fonts ──────────────────────────────────────

class TestGetFonts:
    def test_returns_font_pairing(self, engine):
        fonts = engine.get_fonts(ProductType.SAAS)
        assert isinstance(fonts, FontPairing)
        assert fonts.heading_font
        assert fonts.body_font
        assert fonts.mono_font

    def test_google_fonts_url(self, engine):
        fonts = engine.get_fonts(ProductType.ECOMMERCE)
        assert fonts.google_fonts_url.startswith("https://fonts.googleapis.com")


# ── Anti-patterns ─────────────────────────────────────────────────────

class TestAntiPatterns:
    def test_fintech_anti_patterns(self, engine):
        ds = engine.generate_design_system(ProductType.FINTECH)
        assert len(ds.anti_patterns) >= 3
        joined = " ".join(ds.anti_patterns).lower()
        assert "animation" in joined or "playful" in joined

    def test_each_type_has_anti_patterns(self, engine):
        for pt in ProductType:
            ds = engine.generate_design_system(pt)
            assert len(ds.anti_patterns) >= 3, f"{pt.name} needs ≥3 anti-patterns"


# ── Checklist ─────────────────────────────────────────────────────────

class TestChecklist:
    def test_checklist_items_present(self, engine):
        ds = engine.generate_design_system(ProductType.SAAS)
        assert len(ds.checklist) >= 3
        joined = " ".join(ds.checklist).lower()
        assert "contrast" in joined

    def test_checklist_has_touch_target(self, engine):
        ds = engine.generate_design_system(ProductType.CONSUMER_APP)
        joined = " ".join(ds.checklist).lower()
        assert "touch" in joined or "44" in joined


# ── Accessibility grade ───────────────────────────────────────────────

class TestAccessibility:
    def test_healthcare_grade_a(self, engine):
        style = engine.get_style(ProductType.HEALTHCARE)
        assert style.accessibility_grade == "A"

    def test_consumer_app_grade_b_or_better(self, engine):
        style = engine.get_style(ProductType.CONSUMER_APP)
        assert style.accessibility_grade in ("A", "B")


# ── CSS generation ────────────────────────────────────────────────────

class TestCSSGeneration:
    def test_generate_css_variables(self, engine):
        ds = engine.generate_design_system(ProductType.SAAS)
        css = engine.generate_css_variables(ds)
        assert isinstance(css, str)
        assert ":root" in css
        assert "--color-primary" in css
        assert "--font-heading" in css

    def test_css_contains_spacing(self, engine):
        ds = engine.generate_design_system(ProductType.ECOMMERCE)
        css = engine.generate_css_variables(ds)
        assert "--spacing-" in css
        assert "--shadow-" in css


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_none_input_raises(self, engine):
        with pytest.raises((TypeError, ValueError)):
            engine.get_style(None)

    def test_invalid_type_raises(self, engine):
        with pytest.raises((TypeError, ValueError)):
            engine.get_style("not_a_product_type")
