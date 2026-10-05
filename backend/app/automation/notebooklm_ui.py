"""Every NotebookLM UI element the automation touches, in one place.

Each element lists its locator strategies most-stable first. The visible-text
and icon tiers exist as last-resort fallbacks for the Arabic and English UI; no
code outside this module should spell a selector.
"""
from app.automation.locators import LocatorRegistry, tiered
from app.automation.slide_deck import GENERATING_INDICATOR, register_slide_deck


# Element keys
MODAL = "dialog.modal"
DISMISS_KNOWN = "dialog.dismiss_known"
DISMISS_ONBOARDING = "dialog.dismiss_onboarding"
WELCOME_PAGE = "home.welcome_page"
WELCOME_CREATE_BUTTON = "home.create_button"
NEW_NOTEBOOK_BUTTON = "home.new_notebook_button"
NOTEBOOK_EDITOR = "notebook.editor"
ADD_SOURCES_BUTTON = "notebook.add_sources_button"
COPIED_TEXT_OPTION = "source.copied_text_option"
PASTE_TEXT_AREA = "source.paste_text_area"
INSERT_SOURCE_BUTTON = "source.insert_button"
FILE_INPUT = "source.file_input"
SOURCE_TITLE = "source.title"
SLIDE_DECK_BUTTON = "slide_deck.button"
SLIDE_DECK_CARD = "slide_deck.card"
CUSTOMIZE_BUTTON = "slide_deck.customize_button"
SLIDE_DECK_DIALOG = "slide_deck.dialog"
PROMPT_FIELD = "slide_deck.prompt_field"
ARTIFACT_ITEM = "artifact.slide_deck_item"
ARTIFACT_MORE_BUTTON = "artifact.more_button"
ARTIFACT_DOWNLOAD_PDF = "artifact.download_pdf"
ARTIFACT_OPEN_CARD = "artifact.open_card"
DOWNLOAD_CONTROL = "download.control"
OVERFLOW_MENU_BUTTON = "download.overflow_menu_button"
DOWNLOAD_MENU_ITEM = "download.menu_item"
HAMBURGER_BUTTON = "download.hamburger_button"
HAMBURGER_MENU_ITEM = "download.hamburger_menu_item"
HAMBURGER_OWNER_BUTTON = "download.hamburger_owner_button"

# Selectors that need a value are filled from `params`; the caller quotes it.
_TITLE_TEXT = ":text({text})"


def build_registry() -> LocatorRegistry:
    registry = register_slide_deck(LocatorRegistry())

    # --- dialogs -----------------------------------------------------------
    registry.register(
        MODAL,
        tiered(structure=("[role='dialog'], [role='alertdialog'], [aria-modal='true']",)),
        screen="any",
    )
    registry.register(
        DISMISS_KNOWN,
        tiered(
            text=tuple(
                f"{scope} button:has-text('{label}')"
                for scope, label in (
                    ("[role='dialog']", "Got it"),
                    ("[role='dialog']", "Dismiss"),
                    ("[role='dialog']", "Accept all"),
                    ("[role='dialog']", "موافق"),
                    ("[role='dialog']", "فهمت"),
                    ("[role='dialog']", "حسنًا"),
                    ("[role='dialog']", "لنبدأ"),
                    ("[role='dialog']", "ابدأ"),
                    ("[role='dialog']", "Get started"),
                    ("[role='dialog']", "Let's get started"),
                    ("[role='dialog']", "تجاهل"),
                    ("[role='dialog']", "OK"),
                    ("[role='alertdialog']", "OK"),
                    ("[role='alertdialog']", "حسنًا"),
                    ("[role='alertdialog']", "لنبدأ"),
                    ("[role='alertdialog']", "ابدأ"),
                    ("[role='alertdialog']", "Get started"),
                )
            )
        ),
        screen="onboarding_dialog",
    )
    registry.register(
        DISMISS_ONBOARDING,
        tiered(
            text=tuple(
                f"button:has-text('{label}')"
                for label in (
                    "حسنًا", "لنبدأ", "ابدأ", "OK", "Get started", "Let's get started", "Got it",
                    "I understand", "موافق", "فهمت", "Continue", "Next", "Dismiss", "Close",
                    "تجاهل", "إغلاق",
                )
            )
        ),
        screen="onboarding_dialog",
    )

    # --- home ---------------------------------------------------------------
    registry.register(
        WELCOME_PAGE,
        tiered(structure=("welcome-page, .welcome-page-container",)),
        screen="home",
    )
    registry.register(
        WELCOME_CREATE_BUTTON,
        tiered(
            structure=("button.create-new-button, .create-new-button",),
            aria=("[aria-label*='إنشاء ورقة ملاحظات جديدة']",),
        ),
        screen="home",
    )
    registry.register(
        NEW_NOTEBOOK_BUTTON,
        tiered(
            structure=("button.create-new-button",),
            aria=(
                "[aria-label='إنشاء دفتر ملاحظات']",
                "[aria-label='إنشاء دفتر ملاحظات جديد']",
                "[aria-label='إضافة ملاحظة جديدة']",
                "[aria-label='Create new note']",
                "[aria-label='Create new notebook']",
                "[aria-label='Create new']",
                "[aria-label='New notebook']",
                "[aria-label='New note']",
                "[aria-label='إنشاء ورقة ملاحظات جديدة']",
            ),
            text=(
                "button:has-text('إنشاء دفتر ملاحظات')",
                "button:has-text('إنشاء دفتر ملاحظات جديد')",
                "button:has-text('إضافة ملاحظة جديدة')",
                "button:has-text('Add note')",
                "button:has-text('New note')",
                "button:has-text('New notebook')",
                "button:has-text('Create new note')",
                "button:has-text('Create new notebook')",
                "button:has-text('Create notebook')",
                "button:has-text('Create new')",
                "button:has-text('دفتر ملاحظات جديد')",
                "button:has-text('New Notebook')",
                "div:has-text('إضافة ملاحظة جديدة')",
                "div:has-text('New note')",
                "div:has-text('Create new')",
            ),
        ),
        screen="home",
        required=True,
    )

    # --- notebook and sources ----------------------------------------------
    registry.register(
        NOTEBOOK_EDITOR,
        tiered(
            structure=(
                ".notebook-header-container, .notebook-page, .notebook-editor",
                "textarea, [contenteditable='true']",
            )
        ),
        required=True,
    )
    registry.register(
        ADD_SOURCES_BUTTON,
        tiered(
            aria=(
                "button[aria-label='إضافة مصدر']",
                "button[aria-label='Add sources']",
                "[aria-label='إضافة مصدر']",
                "[aria-label='Add sources']",
            ),
            text=(
                "button:has-text('إضافة مصادر')",
                "button:has-text('Add sources')",
                "button:has-text('إضافة مصدر')",
            ),
        ),
        required=True,
    )
    registry.register(
        COPIED_TEXT_OPTION,
        tiered(
            text=(
                "button:has-text('Copied text')",
                "button:has-text('Text')",
                "mat-card:has-text('Copied text')",
                "button:has-text('نص منسوخ')",
            )
        ),
        screen="add_sources_dialog",
    )
    registry.register(
        PASTE_TEXT_AREA,
        tiered(
            structure=(
                "textarea[placeholder*='الصق النص'], textarea[placeholder*='Paste text']",
                "[role='dialog'] textarea",
            )
        ),
        pick="last",
        screen="paste_text_dialog",
    )
    registry.register(
        INSERT_SOURCE_BUTTON,
        tiered(
            text=(
                "[role='dialog'] button:has-text('إدراج'), "
                "[role='dialog'] button:has-text('Insert'), "
                "[role='dialog'] button:has-text('Save')",
            )
        ),
        pick="last",
        screen="paste_text_dialog",
    )
    registry.register(
        FILE_INPUT,
        tiered(structure=("input[type='file']",)),
        screen="add_sources_dialog",
        hidden_ok=True,
    )
    registry.register(SOURCE_TITLE, tiered(text=(_TITLE_TEXT,)))

    # --- slide deck ---------------------------------------------------------
    registry.register(
        SLIDE_DECK_BUTTON,
        tiered(
            structure=("basic-create-artifact-button[aria-label='مجموعة الشرايح']",),
            aria=(
                "div[role='button'][aria-label='مجموعة شرائح']",
                "button[aria-label=' مجموعة الشرايح']",
                "[aria-label=' مجموعة الشرايح']",
                "[role='button'][aria-label=' مجموعة الشرايح']",
                "[aria-label*='Slide Deck']",
                "[aria-label*='عرض شرائح']",
            ),
            text=(
                "button:has-text('مجموعة الشرايح')",
                "button:has-text('Slide Deck')",
                "button:has-text('Slides')",
                "[role='button']:has-text(' مجموعة الشرائح')",
                "button:has-text('عرض شرائح')",
            ),
        ),
        required=True,
    )
    # Resolved with the Slide Deck button as scope: the card that holds it.
    registry.register(
        SLIDE_DECK_CARD,
        tiered(structure=("xpath=ancestor::*[self::div or self::mat-card][1]",)),
    )
    registry.register(
        CUSTOMIZE_BUTTON,
        tiered(
            aria=("button[aria-label*='ustom'], button[title*='ustom']",),
            text=("button:has-text('Customize'), button:has-text('تخصيص')",),
        ),
    )
    registry.register(
        SLIDE_DECK_DIALOG,
        tiered(structure=("configurable-form-dialog",)),
        screen="slide_deck_dialog",
    )
    registry.register(
        PROMPT_FIELD,
        tiered(structure=("textarea, [contenteditable='true']",)),
        screen="slide_deck_dialog",
    )

    # --- finished artifact and downloads -----------------------------------
    registry.register(
        ARTIFACT_ITEM,
        tiered(
            structure=(
                "artifact-library-item:has(button[aria-description='مجموعة الشرائح']), "
                "artifact-library-item:has(button[aria-description='Slide Deck'])",
            )
        ),
        pick="last",
        screen="artifact",
    )
    registry.register(
        ARTIFACT_MORE_BUTTON,
        tiered(aria=("button[aria-label='المزيد'], button[aria-label*='More']",)),
        pick="last",
        screen="artifact",
    )
    registry.register(
        ARTIFACT_DOWNLOAD_PDF,
        tiered(
            text=(
                "[role='menuitem']:has-text('تنزيل مستند PDF'), "
                "[role='menuitem']:has-text('Download PDF')",
            )
        ),
        pick="last",
        screen="artifact_menu",
    )
    registry.register(
        ARTIFACT_OPEN_CARD,
        tiered(
            aria=("[aria-label*='Open Slide Deck']",),
            text=(
                "button:has-text('Slide Deck'):not(:has-text('Generate'))",
                "button:has-text('عرض الشرائح')",
            ),
        ),
        screen="artifact",
    )
    registry.register(
        DOWNLOAD_CONTROL,
        tiered(
            structure=("a[download]",),
            aria=(
                "button[aria-label*='Download']",
                "button[title*='Download']",
                "button[aria-label*='تنزيل']",
            ),
            text=("button:has-text('Download')", "button:has-text('تنزيل')"),
        ),
        pick="last",
        screen="artifact",
    )
    registry.register(
        OVERFLOW_MENU_BUTTON,
        tiered(aria=("button[aria-label*='More']", "button[aria-label*='المزيد']")),
        screen="artifact",
    )
    registry.register(
        DOWNLOAD_MENU_ITEM,
        tiered(
            text=("[role='menuitem']:has-text('Download')", "[role='menuitem']:has-text('تنزيل')")
        ),
        pick="last",
        screen="artifact_menu",
    )
    registry.register(
        HAMBURGER_BUTTON,
        tiered(
            structure=("button.source-item-more-button", "button.artifact-more-button"),
            aria=(
                "button[aria-label='المزيد']",
                "button[aria-label*='More']",
                "button[mattooltip='المزيد']",
                "button[title='المزيد']",
            ),
            # 'more_vert' is the Material icon name, not user-facing text.
            icon=("button:has(mat-icon:has-text('more_vert'))", "mat-icon:has-text('more_vert')"),
        ),
        screen="artifact",
    )
    registry.register(
        HAMBURGER_MENU_ITEM,
        tiered(
            text=(
                "[role='menuitem']:has-text('تنزيل مستند PDF'), "
                "[role='menuitem']:has-text('Download PDF'), "
                "[role='menuitem']:has-text('Download'), "
                "[role='menuitem']:has-text('تنزيل')",
            )
        ),
        screen="artifact_menu",
    )
    # Resolved with an icon inside a button as scope: the button that owns it.
    registry.register(
        HAMBURGER_OWNER_BUTTON,
        tiered(structure=("xpath=ancestor::button[1]",)),
        screen="artifact",
    )
    return registry


def page_has_landed(page, registry: LocatorRegistry) -> bool:
    """True once NotebookLM has rendered something we can act on, or the login page."""
    if "accounts.google.com" in page.url or "signin" in page.url:
        return True
    return any(
        registry.find(page, key) is not None
        for key in (NEW_NOTEBOOK_BUTTON, NOTEBOOK_EDITOR, WELCOME_PAGE)
    )


__all__ = ["build_registry", "page_has_landed", "GENERATING_INDICATOR"]
