from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_package_declares_pwa_plugin() -> None:
    package = json.loads(read("package.json"))
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert "vite-plugin-pwa" in deps
    assert package["scripts"].get("pwa:validate") == "python3 tests/validate_pwa.py"


def test_vite_pwa_manifest_and_runtime_cache() -> None:
    config = read("vite.config.ts")
    expectations = {
        "VitePWA": r"VitePWA",
        "display standalone": r"display:\s*['\"]standalone['\"]",
        "latest NetworkFirst": r"latest\.json[\s\S]+?handler:\s*['\"]NetworkFirst['\"]",
        "details StaleWhileRevalidate": r"story_[\s\S]+?handler:\s*['\"]StaleWhileRevalidate['\"]",
        "archive CacheFirst": r"archive[\s\S]+?handler:\s*['\"]CacheFirst['\"]",
        "navigate fallback": r"navigateFallback",
    }
    for label, pattern in expectations.items():
        assert re.search(pattern, config), label


def test_index_has_mobile_metadata() -> None:
    index = read("index.html")
    for expected in [
        "theme-color",
        "apple-mobile-web-app-capable",
        "apple-mobile-web-app-title",
        "apple-touch-icon",
        "mobile-web-app-capable",
    ]:
        assert expected in index


def test_icons_exist() -> None:
    for icon in [
        "public/icons/icon-192.png",
        "public/icons/icon-512.png",
        "public/icons/maskable-192.png",
        "public/icons/maskable-512.png",
        "public/apple-touch-icon.png",
        "public/favicon.svg",
    ]:
        assert (ROOT / icon).exists(), icon


def test_app_exposes_install_offline_and_update_ux() -> None:
    app = read("src/App.tsx")
    for expected in [
        "beforeinstallprompt",
        "navigator.onLine",
        "Nova versão disponível",
        "última atualização salva",
        "Instalar app",
        "Adicionar à Tela de Início",
    ]:
        assert expected in app


def test_pwa_documentation_exists() -> None:
    docs = read("docs/pwa.md")
    for expected in ["Android", "iOS", "latest.json", "CacheFirst", "offline"]:
        assert expected in docs


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("PWA validation passed")
