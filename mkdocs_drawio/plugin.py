""" MkDocs Drawio Plugin """

import re
import json
import string
import logging
from urllib.parse import unquote
from lxml import etree
from typing import Dict
from html import escape
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from mkdocs.plugins import BasePlugin
from mkdocs.config import base, config_options as c
from mkdocs.utils import copy_file
from collections import namedtuple
from markdown import markdown

SUB_TEMPLATE = string.Template(
    '<div class="mxgraph" style="background-color: $background;" data-mxgraph="$config"></div>'
)

LOGGER = logging.getLogger("mkdocs.plugins.diagrams")


class Toolbar(base.Config):
    """Configuration options for the toolbar, mostly taken from
    https://www.drawio.com/doc/faq/embed-html-options
    """

    pages = c.Type(bool, default=True)
    """ Display the page selector in the toolbar """

    zoom = c.Type(bool, default=True)
    """ Display the zoom control in the toolbar """

    layers = c.Type(bool, default=True)
    """ Display the layers control in the toolbar """

    lightbox = c.Type(bool, default=True)
    """ Display the open in lightbox control in the toolbar """

    position = c.Choice(["top", "bottom"], default="top")
    """ Position of the toolbar """

    no_hide = c.Type(bool, default=False)
    """ Whether to hide the toolbar when the mouse is not over it """


class DrawioConfig(base.Config):
    """Configuration options for the Drawio Plugin"""

    toolbar = c.SubConfig(Toolbar)
    """ Whether to show the toolbar with controls """

    tooltips = c.Type(bool, default=True)
    """ Whether to show tooltips """

    border = c.Optional(c.Type(int))
    padding = c.Type(int, default=10)
    """ Padding around the diagram, border will be deprecated
    but kept for backwards compatibility """

    edit = c.Type((bool, str), default=False)
    """ Whether to allow editing the diagram or use a custom editor URL """

    background = c.Type(str, default="transparent")

    include_src = c.Type(bool, default=True)
    include_page = c.Type(bool, default=True)
    caption_prefix = c.Type(str, default="Figure: ")
    caption_page_separator = c.Type(str, default=" - ")

    def _post_validate(self):
        if self.border is not None:
            self.padding = self.border

        return super()._post_validate()


class DrawioPlugin(BasePlugin[DrawioConfig]):
    """
    Plugin for embedding Drawio Diagrams into your MkDocs
    """

    RE_DRAWIO_FILE = re.compile(r".*\.drawio$", re.IGNORECASE)

    def on_config(self, config: base.Config):
        """Add the drawio viewer library to the site"""
        self.base = Path(__file__).parent
        self.css = ["css/drawio.css"]
        self.js = ["js/drawio.js", "js/viewer-static.min.js"]

        config.extra_css.extend(self.css)
        config.extra_javascript.extend(self.js)

    def on_post_build(self, config: base.Config):
        from mkdocs.utils import copy_file
        from pathlib import Path

        base = Path(__file__).parent
        css_files = ["css/drawio.css"]
        js_files = ["js/drawio.js", "js/viewer-static.min.js"]

        site = Path(config["site_dir"])

        # Copy CSS  
        for path in css_files:
            src = base / path
            dst = site / path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                print(f"✅ Copying CSS: {src} → {dst}")
                copy_file(src, dst)
            else:
                print(f"❌ CSS file not found: {src}")

        # Copy JS
        for path in js_files:
            src = base / path
            dst = site / path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                print(f"✅ Copying JS: {src} → {dst}")
                copy_file(src, dst)
            else:
                print(f"❌ JS file not found: {src}")

        # Copy fonts
        fonts_src = base / "fonts"
        fonts_dst = site / "fonts"
        fonts_dst.mkdir(parents=True, exist_ok=True)

        for font_file in fonts_src.glob("*.ttf"):
            print(f"📦 Copying font: {font_file.name}")
            copy_file(font_file, fonts_dst / font_file.name)

    def get_diagram_config(self, diagram: Tag) -> Dict:
        """Get the configuration for the diagram. Apply either default values in the plugin
        or values passed in the diagram tag from `attr_list` markdown extension."""

        # Coercion functions
        def no_action(x):
            return x

        def to_bool(x):
            if isinstance(x, bool):
                return x
            if x.lower() in ["true", "1", "yes"]:
                return True
            if x.lower() in ["false", "0", "no"]:
                return False
            LOGGER.warning(f'Could not parse boolean value "{x}"')
            return False

        def to_int_or_str(x):
            try:
                return int(x)
            except ValueError:
                return x

        class to_str:
            def __init__(self, text):
                self.text = text

            def __call__(self, enabled):
                return self.text if enabled else ""

        # To add more options described in https://www.drawio.com/doc/faq/embed-html-options
        # Add a new tuple to the list with the following format:
        T = namedtuple("EmbedOption", ["attr", "name", "default", "coerce"])
        embed_options = [
            T("data-page", "page", None, to_int_or_str),
            T("data-layers", "layers", None, no_action),
            T("data-zoom", "zoom", None, no_action),
            T(
                "data-edit",
                "edit",
                self.config.edit,
                lambda x: (
                    "_blank" if x is True else (
                        f"{x}&client=1" if isinstance(x, str) and "?" in x else f"{x}?client=1"
                    ) if isinstance(x, str) else None
                ),
            ),
            T("data-padding", "border", self.config.padding, lambda x: int(x) + 5),
            T("data-tooltips", "tooltips", self.config.tooltips, to_bool),
            T(
                "data-toolbar-position",
                "toolbar-position",
                self.config.toolbar.position,
                no_action,
            ),
            T("data-title", "title", None, no_action),
            T("data-nohide", "toolbar-nohide", self.config.toolbar.no_hide, to_bool),
            T(
                "data-toolbar-pages",
                "toolbar",
                self.config.toolbar.pages,
                to_str("pages"),
            ),
            T("data-toolbar-zoom", "toolbar", self.config.toolbar.zoom, to_str("zoom")),
            T(
                "data-toolbar-layers",
                "toolbar",
                self.config.toolbar.layers,
                to_str("layers"),
            ),
            T(
                "data-toolbar-lightbox",
                "toolbar",
                self.config.toolbar.lightbox,
                to_str("lightbox"),
            ),
        ]

        # Get the data-attributes from the diagram tag
        conf = {}
        for option in embed_options:
            value = None
            if option.default is not None:
                value = option.coerce(option.default)
            if option.attr in diagram.attrs:
                value = option.coerce(diagram.attrs[option.attr])
            if value is None:
                continue
            if option.name in conf and isinstance(conf[option.name], str):
                conf[option.name] += f" {value}"
            else:
                conf[option.name] = value

        conf["toolbar"] = conf["toolbar"].strip()
        if conf["toolbar"] == "":
            del conf["toolbar"]
                
        # Set the fonts for the Mondrian Diagram viewer
        conf["defaultFonts"] = [
            {
                "fontFamily": "Roboto Medium",
                "fontUrl": "fonts/Roboto-Medium.ttf"
            },
            {
                "fontFamily": "Roboto",
                "fontUrl": "fonts/Roboto-Regular.ttf"
            },
            {
                "fontFamily": "Roboto Condensed",
                "fontUrl": "fonts/RobotoCondensed-Regular.ttf"
            },
            {
                "fontFamily": "Roboto Mono",
                "fontUrl": "fonts/RobotoMono-Regular.ttf"
            }
        ]

        viewer_bg = diagram.attrs.get("background", self.config.background)
        conf["viewerBackground"] = viewer_bg

        return conf

    def render_drawio_diagrams(self, output_content, page):
        """Backwards compatibility with mkdocs-print-site."""
        return self.on_post_page(output_content, self.config, page)

    def on_post_page(self, output_content, config, page):
        if ".drawio" not in output_content.lower():
            LOGGER.debug(f"⏭️  Skipped page: {page.file.src_path} (no .drawio)")
            return output_content

        LOGGER.debug(f"🔧 Processing page: {page.file.src_path}")
        result = self._process_drawio_page(output_content, config, page)

        return result

    def _process_drawio_page(self, output_content, config, page):
        if ".drawio" not in output_content.lower():
            return output_content

        path = Path(page.file.abs_dest_path).parent
        soup = BeautifulSoup(output_content, "lxml")

        diagrams = soup.find_all("img", src=self.RE_DRAWIO_FILE)
        LOGGER.debug(f"🔍 Found {len(diagrams)} diagrams in {page.file.src_path}")

        for idx, diagram in enumerate(diagrams):
            diagram_config = self.get_diagram_config(diagram)

            if re.search("^https?://", diagram["src"]):
                mxgraph = BeautifulSoup(
                    self.substitute_with_url(diagram_config, diagram["src"]),
                    "lxml",
                )
            else:
                # Resolve pages
                pages_attr = diagram.attrs.get("data-pages")
                if pages_attr:
                    requested_pages = [p.strip() for p in pages_attr.split(",")]
                elif diagram.get("alt"):  # ← use alt as a fallback
                    requested_pages = [diagram.get("alt").strip()]
                else:
                    requested_pages = None  # ← render all pages

                html_str, page_names = self.substitute_with_file(diagram_config, path, diagram["src"], requested_pages, page.file.src_path)

                mxgraph = BeautifulSoup(html_str, "lxml")

            container = soup.new_tag("div", **{"class": "drawio-container"})
            for elem in mxgraph:
                container.append(elem)

            caption_text = diagram.attrs.get("data-caption")
            caption_wrapper = None

            def resolve_flag(val, fallback):
                if val is None:
                    return fallback
                if isinstance(val, str):
                    if val.lower() in ("false", "0", "none"):
                        return False
                    if val.lower() in ("true", "1", "yes"):
                        return True
                    return val
                return val

            include_src = resolve_flag(diagram.attrs.get("data-caption-src"), self.config.include_src)
            include_page = resolve_flag(diagram.attrs.get("data-caption-page"), self.config.include_page)
            include_prefix = resolve_flag(diagram.attrs.get("data-caption-prefix"), self.config.caption_prefix)
            caption_prefix = "" if not include_prefix else diagram.attrs.get("data-caption-prefix", self.config.caption_prefix)
            caption_page_separator = diagram.attrs.get("data-caption-page-separator", self.config.caption_page_separator)

            if caption_text is not None:
                full_caption = f"{caption_prefix}{caption_text}" if caption_prefix else caption_text
            else:
                parts = []
                if include_src:
                    src_clean = unquote(diagram["src"])
                    src_label = include_src if isinstance(include_src, str) else Path(src_clean).stem
                    parts.append(src_label)
                if include_page:
                    page_label = include_page if isinstance(include_page, str) else ", ".join(page_names)
                    if page_label:
                        parts.append(page_label)
                full_caption = f"{caption_prefix}{caption_page_separator.join(parts)}" if parts else None

            if full_caption:
                caption_html = markdown(full_caption)
                caption_soup = BeautifulSoup(caption_html, "lxml")
                caption_wrapper = soup.new_tag("div", **{"class": "md-caption drawio-caption"})
                for node in caption_soup:
                    caption_wrapper.append(node)

            wrapper = diagram
            while wrapper and wrapper.name not in ("body", "[document]"):
                if "glightbox" in wrapper.get("class", []):
                    break
                wrapper = wrapper.parent

            if not wrapper or wrapper.name in ("body", "[document]"):
                wrapper = diagram

            wrapper.replace_with(container)
            if caption_wrapper:
                container.insert_after(caption_wrapper)

        return str(soup)

    def substitute_with_url(self, config: Dict, url: str) -> str:
        config["url"] = url
        return SUB_TEMPLATE.substitute(background=config.get("viewerBackground", "transparent"),config=escape(json.dumps(config)))

    def substitute_with_file(
        self,
        config: Dict,
        path: Path,
        src: str,
        pages: list[str] | None,
        markdown_file: str,
    ) -> tuple[str, list[str]]:
        resolved_path = None
        try:
            decoded_src = unquote(src.strip('"').strip("'"))

            if decoded_src.startswith("/"):
                docs_root = Path("docs").resolve()
                resolved_path = docs_root.joinpath(decoded_src[1:]).resolve()
            else:
                resolved_path = path.joinpath(decoded_src).resolve()

            diagram_xml = etree.parse(resolved_path)

        except Exception as e:
            LOGGER.warning(f"❌ Could not parse diagram file '{src}' — {e}")
            return self._styled_error_html(f"Failed to load <b>{src}</b>"), []

        diagrams = diagram_xml.xpath("//diagram")

        if not diagrams:
            LOGGER.warning(f"❌ No diagrams found in '{src}'")
            return self._styled_error_html(f"No diagrams found in <b>{src}</b>"), []

        all_available = [d.get("name") or str(i) for i, d in enumerate(diagrams)]

        # ✅ Expand input pages
        if pages is None:
            pages = all_available
        else:
            expanded_pages = []
            seen = set()
            duplicates = set()

            for page in pages:
                page = page.strip()
                resolved = []

                if page == "@first":
                    resolved = ["0"]
                elif page == "@last":
                    resolved = [str(len(diagrams) - 1)]
                elif re.match(r"^\d+-\d+$", page):
                    try:
                        start, end = map(int, page.split("-"))
                        resolved = [str(i) for i in range(start, end + 1)]
                    except Exception:
                        LOGGER.warning(f"⚠️ Invalid range '{page}' in '{markdown_file}'")
                        continue
                else:
                    resolved = [page]

                for r in resolved:
                    if r not in seen:
                        seen.add(r)
                        expanded_pages.append(r)
                    else:
                        duplicates.add(r)

            if duplicates:
                dup_list = ", ".join(sorted(duplicates))
                LOGGER.warning(
                    f"⚠️ Duplicate page references removed while processing diagram '{resolved_path.name}' "
                    f"in Markdown file '{markdown_file}' — duplicates: {dup_list}"
                )

            pages = expanded_pages

        # Create new mxfile XML container
        parser = etree.XMLParser()
        mxfile_el = parser.makeelement("mxfile")
        page_names = []

        for page in pages:
            selected = None
            actual_name = None

            # Match by name
            for d in diagrams:
                if d.get("name") == page:
                    selected = d
                    break

            # Fallback to index
            if selected is None and page.isdigit():
                index = int(page)
                if 0 <= index < len(diagrams):
                    selected = diagrams[index]

            if selected is not None:
                try:
                    clone = etree.fromstring(etree.tostring(selected))
                    mxfile_el.append(clone)
                    actual_name = selected.get("name") or str(index if 'index' in locals() else page)
                    page_names.append(actual_name)
                except Exception as e:
                    LOGGER.warning(f"⚠️ Could not clone diagram '{page}' from '{src}' — {e}")
            else:
                LOGGER.warning(f"⚠️ No diagram found for page '{page}' in '{src}'")

        # 🧩 Handle case: no pages matched
        if len(mxfile_el) == 0:
            LOGGER.warning(f"❌ No matching pages rendered for '{src}' (filtered set was empty)")
            available_list = ", ".join(escape(name) for name in all_available)
            requested_list = ", ".join(escape(p) for p in pages)
            return self._styled_error_html(
                f"No matching pages found in <b>{src}</b><br>"
                f"Requested: <b>{requested_list}</b><br>"
                f"Available: <b>{available_list}</b>"
            ), []

        config["xml"] = etree.tostring(mxfile_el, encoding=str)

        if page_names:
            config["title"] = page_names[0]

        return SUB_TEMPLATE.substitute(
            background=config.get("viewerBackground", "transparent"),
            config=escape(json.dumps(config))
        ), page_names


    def parse_diagram(self, data, page_name, src="", path=None) -> tuple[str, str]:
        if page_name is None or len(page_name) == 0:
            return etree.tostring(data, encoding=str), None

        try:
            mxfile = data.xpath("//mxfile")[0]
            diagrams = mxfile.xpath("//diagram")

            selected = None

            # Try to match by name
            named_matches = [d for d in diagrams if d.get("name") == page_name]
            if named_matches:
                selected = named_matches[0]
            # Fallback to index
            elif page_name.isdigit():
                index = int(page_name)
                if 0 <= index < len(diagrams):
                    selected = diagrams[index]

            if selected is not None:
                actual_name = selected.get("name", None)
                parser = etree.XMLParser()
                result = parser.makeelement(mxfile.tag, mxfile.attrib)
                result.append(selected)
                return etree.tostring(result, encoding=str), actual_name

            LOGGER.warning(f"No diagram found for name or index '{page_name}' in '{src}' at '{path}'")
            return etree.tostring(mxfile, encoding=str), None

        except Exception as e:
            LOGGER.warning(f"Could not parse page '{page_name}' for diagram '{src}' on path '{path}' — {e}")
            return "", None

    def _styled_error_html(self, message: str) -> str:
        return f'''
        <div class="drawio-error" style="
            background-color: #fff0f0;
            color: #a00000;
            padding: 1em;
            border: 1px solid #ff0000;
            font-family: monospace;
            margin-bottom: 1em;
        ">
            <span style="font-size: 1.2em; margin-right: 0.3em;">❌</span>{message}
        </div>
        '''
