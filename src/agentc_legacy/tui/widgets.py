from dataclasses import dataclass
from typing import Callable, Any
from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.filters import FilterOrBool

"""TUI scroll helpers.

Contains:
- ScrollablePaneConfig: configuration container for InstrumentedScrollablePane
- ScrollEvents: small callback registry for layout-change events
- InstrumentedScrollablePane: ScrollablePane that exposes visible/virtual heights and fires layout events
- ScrollController: high-level scroll control (line/page/auto-follow) over an InstrumentedScrollablePane
"""

@dataclass
class ScrollablePaneConfig:
    """Configuration options passed to InstrumentedScrollablePane."""
    keep_cursor_visible: FilterOrBool = True
    keep_focused_window_visible: FilterOrBool = True
    show_scrollbar: FilterOrBool = True

class ScrollEvents:
    """A tiny callback registry for layout-change events."""

    def __init__(self) -> None:
        self._layout_change_callbacks: list[Callable[[int, int], None]] = []

    def on_layout_change(self, callback: Callable[[int, int], None]) -> None:
        """Register a callback(visible_height, virtual_height)."""
        self._layout_change_callbacks.append(callback)

    def remove_layout_change(self, callback: Callable[[int, int], None]) -> None:
        """Remove a previously registered layout-change callback."""
        try:
            self._layout_change_callbacks.remove(callback)
        except ValueError:
            # Silently ignore attempts to remove non-registered callbacks.
            pass

    def fire_layout_change(self, visible_height: int, virtual_height: int) -> None:
        """Invoke every registered layout-change callback."""
        for callback in list(self._layout_change_callbacks):
            callback(visible_height, virtual_height)

class InstrumentedScrollablePane(ScrollablePane):
    """ScrollablePane that tracks visible and virtual heights and publishes layout events."""

    def __init__(
        self,
        content: Any,
        config: ScrollablePaneConfig | None = None,
        **kwargs: Any,
    ) -> None:
        config = config or ScrollablePaneConfig()
        super().__init__(
            content,
            keep_cursor_visible=config.keep_cursor_visible,
            keep_focused_window_visible=config.keep_focused_window_visible,
            show_scrollbar=config.show_scrollbar,
            **kwargs,
        )
        self.events = ScrollEvents()
        self.visible_height: int = 0
        self.virtual_height: int = 0

    def write_to_screen(
        self,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        parent_style: str,
        erase_bg: bool,
        z_index: int | None,
    ) -> None:
        # Mirror prompt_toolkit's base-class layout calculations (visible/virtual heights,
        # available width accounting for scrollbar) so external controllers can clamp or
        # auto-follow scroll values reliably before delegating to the base implementation.
        show_scrollbar = self.show_scrollbar()
        virtual_width = (
            write_position.width - 1 if show_scrollbar else write_position.width
        )
        # Query the content for its preferred height given the available width / height.
        virtual_height = self.content.preferred_height(
            virtual_width, self.max_available_height
        ).preferred
        virtual_height = max(virtual_height, write_position.height)
        virtual_height = min(virtual_height, self.max_available_height)

        self.visible_height = write_position.height
        self.virtual_height = virtual_height

        self.events.fire_layout_change(self.visible_height, self.virtual_height)

        super().write_to_screen(
            screen, mouse_handlers, write_position, parent_style, erase_bg, z_index
        )

class ScrollController:
    """Controller for smooth scrolling and auto-follow behavior on an InstrumentedScrollablePane."""

    def __init__(
        self,
        pane: InstrumentedScrollablePane,
        invalidate_callback: Callable[[], None],
        snap_threshold: int = 1,
    ) -> None:
        if not isinstance(pane, InstrumentedScrollablePane):
            raise TypeError("pane must be an InstrumentedScrollablePane")
        if snap_threshold < 0:
            raise ValueError("snap_threshold must be non-negative")

        self.pane: InstrumentedScrollablePane = pane
        self._invalidate: Callable[[], None] = invalidate_callback
        self._auto_follow: bool = True
        self._pending_follow: bool = False
        self._snap_threshold: int = snap_threshold

        # Subscribe to layout-change events to handle pending follow requests.
        self.pane.events.on_layout_change(self._on_layout_change)

    @property
    def is_auto_following(self) -> bool:
        """Return whether the controller will keep the view auto-following at the bottom."""
        return self._auto_follow

    def scroll_lines(self, amount: int) -> None:
        """Scroll by a specified number of lines."""
        if amount == 0:
            return
        self._scroll(amount)

    def scroll_pages(self, amount: int) -> None:
        """Scroll by a number of 'pages' (visible_height - 1)."""
        if amount == 0:
            return
        page = max(1, self.pane.visible_height - 1)
        self._scroll(amount * page)

    def scroll_to_top(self) -> None:
        """Stop auto-follow and go to the top of the buffer."""
        self._pending_follow = False
        if self._set_scroll(0):
            self._auto_follow = False

    def scroll_to_bottom(self) -> None:
        """Enable auto-follow and schedule follow behavior."""
        self._auto_follow = True
        self._pending_follow = False
        self.follow_output_if_allowed()
        self.request_follow()

    def request_follow(self) -> None:
        """If auto-follow is enabled, mark a pending follow and request a redraw."""
        if not self._auto_follow:
            return
        self._pending_follow = True
        self._invalidate()

    def follow_output_if_allowed(self, *, invalidate: bool = True) -> None:
        """If auto-follow is enabled, move the pane to its maximum scroll position."""
        if not self._auto_follow:
            self._pending_follow = False
            return
        desired = self._max_scroll()
        if self.pane.vertical_scroll != desired:
            self.pane.vertical_scroll = desired
            if invalidate:
                self._invalidate()
        self._pending_follow = False

    def clamp(self) -> None:
        """Clamp current scroll position to the maximum allowed (useful when content shrinks)."""
        max_scroll = self._max_scroll()
        if self.pane.vertical_scroll > max_scroll:
            self._set_scroll(max_scroll)
            self._pending_follow = False

    def _scroll(self, amount: int) -> bool:
        """Internal scroll implementation that updates auto-follow based on proximity to bottom."""
        if self.pane.visible_height == 0:
            return False
        max_scroll = self._max_scroll()
        new_value = max(0, min(self.pane.vertical_scroll + amount, max_scroll))

        if self._set_scroll(new_value):
            # Smart snap-to-bottom: if we're within snap_threshold of the bottom,
            # re-enable auto-follow so subsequent output keeps us at the bottom.
            distance_from_bottom = max_scroll - new_value
            if distance_from_bottom <= self._snap_threshold:
                self._auto_follow = True
            else:
                self._auto_follow = False

            self._pending_follow = False
            return True
        return False

    def _max_scroll(self) -> int:
        """Compute the maximum scroll offset available."""
        if self.pane.visible_height == 0:
            return 0
        return max(0, self.pane.virtual_height - self.pane.visible_height)

    def _set_scroll(self, value: int) -> bool:
        """Set the scroll to a bounded value and request invalidation if changed."""
        if self.pane.visible_height == 0:
            return False
        bounded = max(0, min(value, self._max_scroll()))
        if bounded != self.pane.vertical_scroll:
            self.pane.vertical_scroll = bounded
            self._invalidate()
            return True
        return False

    def _on_layout_change(self, visible_height: int, virtual_height: int) -> None:
        """Handle layout-change events - if we had a pending follow request, attempt it now."""
        if not self._pending_follow:
            return
        self.follow_output_if_allowed(invalidate=False)
