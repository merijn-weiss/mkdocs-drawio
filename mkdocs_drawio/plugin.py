""" MkDocs Drawio Plugin """

import re
import json
import string
import logging
from urllib.parse import unquote, quote, urlparse
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
    zoom = c.Type(bool, default=True)
    layers = c.Type(bool, default=True)
    lightbox = c.Type(bool, default=True)
    position = c.Choice(["top", "bottom"], default="top")
    no_hide = c.Type(bool, default=False)

class DrawioConfig(base.Config):
    toolbar = c.SubConfig(Toolbar)
    tooltips = c.Type(bool, default=True)
    border = c.Optional(c.Type(int))
    padding = c.Type(int, default=10)
    edit = c.Type((bool, str), default=False)
    editor_base_url = c.Optional(c.Type(str, default=None))
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

    def get_diagram_config(self, diagram: Tag, page, src: str = "", page_names=None, diagram_xml=None) -> Dict:
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

        T = namedtuple("EmbedOption", ["attr", "name", "default", "coerce"])
        embed_options = [
            T("data-page", "page", None, to_int_or_str),
            T("data-layers", "layers", None, no_action),
            T("data-zoom", "zoom", None, no_action),
            T(
                "data-edit",
                "edit",
                None,
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
            T("data-toolbar-pages", "toolbar", self.config.toolbar.pages, to_str("pages")),
            T("data-toolbar-zoom", "toolbar", self.config.toolbar.zoom, to_str("zoom")),
            T("data-toolbar-layers", "toolbar", self.config.toolbar.layers, to_str("layers")),
            T("data-toolbar-lightbox", "toolbar", self.config.toolbar.lightbox, to_str("lightbox")),
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
    
    def build_caption(self, diagram: Tag, page_names: list[str], editor_href: str | None) -> Tag | None:
        caption_text = diagram.attrs.get("data-caption")
        include_src = diagram.attrs.get("data-caption-src", self.config.include_src)
        include_page = diagram.attrs.get("data-caption-page", self.config.include_page)
        include_prefix = diagram.attrs.get("data-caption-prefix", self.config.caption_prefix)
        caption_prefix = "" if not include_prefix else diagram.attrs.get("data-caption-prefix", self.config.caption_prefix)
        caption_page_separator = diagram.attrs.get("data-caption-page-separator", self.config.caption_page_separator)

        full_caption = None
        if caption_text:
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
            if parts:
                full_caption = f"{caption_prefix}{caption_page_separator.join(parts)}"

        if full_caption:
            caption_html = markdown(full_caption)
            caption_soup = BeautifulSoup(caption_html, "lxml")
            para = caption_soup.find("p")
            if para and editor_href:
                icon_html = f'''<a class="md-icon drawio-caption-icon" href="{editor_href}" title="Edit this diagram" target="_blank"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M10 20H6V4h7v5h5v3.1l2-2V8l-6-6H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h4zm10.2-7c.1 0 .3.1.4.2l1.3 1.3c.2.2.2.6 0 .8l-1 1-2.1-2.1 1-1c.1-.1.2-.2.4-.2m0 3.9L14.1 23H12v-2.1l6.1-6.1z"/></svg></a>'''
                para.append(BeautifulSoup(icon_html, "lxml").a)
            if para:
                caption_wrapper = caption_soup.new_tag("div", **{"class": "md-caption drawio-caption"})
                caption_wrapper.append(para)
                return caption_wrapper
        return None

    def _process_drawio_page(self, output_content, config, page):
        if ".drawio" not in output_content.lower():
            return output_content

        path = Path(page.file.abs_dest_path).parent
        soup = BeautifulSoup(output_content, "lxml")
        diagrams = soup.find_all("img", src=self.RE_DRAWIO_FILE)

        for diagram in diagrams:
            requested_pages = diagram.attrs.get("data-pages")
            if requested_pages:
                requested_pages = [p.strip() for p in requested_pages.split(",")]
            elif diagram.get("alt"):
                requested_pages = [diagram.get("alt").strip()]
            else:
                requested_pages = None

            config_data = {}
            html_str, page_names = self.substitute_with_file(
                config_data, path, diagram["src"], requested_pages, page.file.src_path
            )

            diagram_config = self.get_diagram_config(diagram, page, diagram["src"], page_names)
            diagram_xml = etree.fromstring(config_data["xml"]) if "xml" in config_data else None
            editor_href = self.inject_edit_link(diagram_config, diagram, diagram_xml, page_names, page)
            diagram_config.update(config_data)

            html_str = SUB_TEMPLATE.substitute(
                background=diagram_config.get("viewerBackground", "transparent"),
                config=escape(json.dumps(diagram_config))
            )

            mxgraph = BeautifulSoup(html_str, "lxml")
            container = soup.new_tag("div", **{"class": "drawio-container"})
            container.extend(mxgraph)

            caption_wrapper = self.build_caption(diagram, page_names, editor_href)

            wrapper = diagram
            while wrapper and wrapper.name not in ("body", "[document]"):
                if "glightbox" in wrapper.get("class", []):
                    break
                wrapper = wrapper.parent
            if not wrapper or wrapper.name in ("body", "[document]"):
                wrapper = diagram

            if caption_wrapper:
                wrapper.insert_after(caption_wrapper)

            wrapper.replace_with(container)

        return str(soup)

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
                LOGGER.debug(f"🔢 Attempting index-based diagram selection: index={index}, total={len(diagrams)}")
                for i, d in enumerate(diagrams):
                    name = d.get("name")
                    LOGGER.debug(f"    🧾 Diagram {i}: name='{name}'")
                if 0 <= index < len(diagrams):
                    selected = diagrams[index]
                    LOGGER.debug(f"✅ Selected diagram at index {index}: name='{selected.get('name')}'")
                else:
                    LOGGER.warning(f"⚠️ Index '{index}' is out of bounds for diagram file '{src}'")

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

        LOGGER.debug(f"[drawio] final viewer config: {json.dumps(config, indent=2)}")

        return SUB_TEMPLATE.substitute(
            background=config.get("viewerBackground", "transparent"),
            config=escape(json.dumps(config))
        ), page_names

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

    def inject_edit_link(self, diagram_config, diagram, diagram_xml, page_names, page):
        config_edit = self.config.edit
        diagram_edit = diagram.attrs.get("data-edit", "").lower()
        if config_edit is False or diagram_edit == "false":
            return None

        if diagram_xml is None or not page_names or page is None:
            return None

        try:
            page_id = None
            for d in diagram_xml.xpath("//diagram"):
                if d.get("name") == page_names[0]:
                    page_id = d.get("id")
                    break

            if not page_id:
                return None

            editor_href = self.build_editor_url(diagram, diagram["src"], page_id, page)
            if editor_href:
                diagram_config["edit"] = f"{editor_href}?client=1"
                toolbar_value = diagram_config.get("toolbar", "")
                if isinstance(toolbar_value, str) and "edit" not in toolbar_value:
                    diagram_config["toolbar"] = f"{toolbar_value.strip()} edit".strip()
                return editor_href
        except Exception as e:
            LOGGER.warning(f"⚠️ Failed to build edit URL — {e}")
        return None

    def build_editor_url(self, diagram: Tag, src: str, page_id: str, page=None) -> str:
        def determine_hash_prefix(base_url: str) -> str:
            """Return the correct hash prefix based on base_url."""
            parsed_url = urlparse(base_url)
            hostname = parsed_url.hostname or ""
            if "github.com" in hostname or "github.io" in hostname:
                return "H"
            return "A"  # Default to GitLab-style paths

        base_url = diagram.attrs.get("data-editor-url", self.config.editor_base_url)
        if not base_url or not page_id:
            LOGGER.warning(f"⚠️ Cannot build editor URL — missing base_url or page_id (base_url={base_url}, page_id={page_id})")
            return ""

        if not page or not getattr(page, "edit_url", None):
            page_file = getattr(page, "file", None)
            if not page_file or not getattr(page_file, "name", "").startswith("print_page"):
                LOGGER.warning(f"⚠️ Cannot build editor URL for diagram '{src}' — page.edit_url not available")
            return ""

        try:
            edit_url = page.edit_url
            LOGGER.debug(f"[build_editor_url] Using edit_url: {edit_url}")

            parsed = urlparse(edit_url)
            path_parts = parsed.path.strip("/").split("/")

            if "edit" not in path_parts:
                LOGGER.warning(f"⚠️ Could not find 'edit' in path: {parsed.path}")
                return ""

            edit_index = path_parts.index("edit")
            repo_prefix = "/".join(path_parts[:edit_index])
            edit_path = "/".join(path_parts[edit_index + 1:])

            if not repo_prefix or not edit_path:
                raise ValueError("Missing repo_prefix or edit_path")

            src_clean = Path(src).as_posix().lstrip("/")
            full_src = f"{repo_prefix}/{edit_path.rsplit('/', 1)[0]}/{src_clean}".lstrip("/")

            # Only encode the actual file name, not the whole path
            src_path = Path(full_src)
            parent = src_path.parent.as_posix()
            filename = quote(unquote(src_path.name), safe="")
            encoded_src = f"{parent}/{filename}"

            encoded_json = quote(json.dumps({"pageId": page_id}))
            hash_prefix = determine_hash_prefix(base_url)
            viewer_url = f"{base_url}#{hash_prefix}{encoded_src}#{encoded_json}"

            LOGGER.debug(f"[build_editor_url] Constructed viewer_url: {viewer_url}")
            return viewer_url

        except Exception as e:
            LOGGER.warning(f"⚠️ Failed to build editor URL for diagram '{src}' — {e}")
            return ""
