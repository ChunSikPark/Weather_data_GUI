"""Sphinx configuration for the Team Overbye Weather Data documentation."""

import os
import sys

sys.path.insert(0, os.path.abspath("../package"))

project = "Team Overbye Weather Data"
copyright = "Texas A&M University, Team Overbye"
author = "Team Overbye"
release = "0.4.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# ── Markdown ────────────────────────────────────────────────────────────────
myst_enable_extensions = ["colon_fence", "deflist", "linkify", "substitution"]
myst_heading_anchors = 3

# ── Autodoc ─────────────────────────────────────────────────────────────────
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}

# ── HTML ────────────────────────────────────────────────────────────────────
html_theme = "sphinx_rtd_theme"
html_title = "Team Overbye Weather Data"
html_static_path = ["_static"]
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 3,
    "titles_only": False,
}
