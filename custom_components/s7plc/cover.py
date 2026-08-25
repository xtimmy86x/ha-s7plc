from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_AREA,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_POSITION_FEEDBACK,
    CONF_COVER_STATUS_ADDRESS,
    CONF_COVER_STATUS_CLOSED_VALUES,
    CONF_COVER_STATUS_CLOSING_VALUES,
    CONF_COVER_STATUS_OPEN_VALUES,
    CONF_COVER_STATUS_OPENING_VALUES,
    CONF_COVER_STATUS_STOPPED_VALUES,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVERS,
    CONF_DEVICE_CLASS,
    CONF_INVERT_POSITION,
    CONF_INVERT_TILT,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_POSITION_COMMAND_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_STOP_COMMAND_ADDRESS,
    CONF_STOP_PULSE_DURATION,
    CONF_TILT_COMMAND_ADDRESS,
    CONF_TILT_STATE_ADDRESS,
    CONF_TOGGLE_MODE,
    CONF_TOGGLE_PULSE_DURATION,
    CONF_UID,
    CONF_USE_STATE_TOPICS,
    DEFAULT_COVER_STATUS_CLOSED_VALUES,
    DEFAULT_COVER_STATUS_CLOSING_VALUES,
    DEFAULT_COVER_STATUS_OPEN_VALUES,
    DEFAULT_COVER_STATUS_OPENING_VALUES,
    DEFAULT_COVER_STATUS_STOPPED_VALUES,
    DEFAULT_OPERATE_TIME,
    DEFAULT_PULSE_DURATION,
    DEFAULT_TOGGLE_MODE,
)
from .entity import S7BaseEntity, async_configure_entity_availability
from .helpers import (
    default_entity_name,
    get_coordinator_and_device_info,
    parse_mode_values,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


def _traditional_feedback_mode(item: dict[str, Any]) -> str:
    """Return the persisted mode, or infer the legacy feedback shape."""
    mode = item.get(CONF_COVER_POSITION_FEEDBACK)
    if mode in {"timed", "opening", "closing", "both", "status"}:
        return mode
    # Before the selector existed, ``use_state_topics`` was authoritative.
    # A status word was independent movement feedback, not position feedback.
    use_state_topics = item.get(CONF_USE_STATE_TOPICS)
    if use_state_topics is False:
        return "timed"
    if use_state_topics is True:
        if item.get(CONF_OPENING_STATE_ADDRESS) and item.get(
            CONF_CLOSING_STATE_ADDRESS
        ):
            return "both"
        if item.get(CONF_OPENING_STATE_ADDRESS):
            return "opening"
        if item.get(CONF_CLOSING_STATE_ADDRESS):
            return "closing"
        # Do not claim feedback which the configuration cannot provide.
        return "timed"
    if item.get(CONF_OPENING_STATE_ADDRESS) and item.get(CONF_CLOSING_STATE_ADDRESS):
        return "both"
    if item.get(CONF_OPENING_STATE_ADDRESS):
        return "opening"
    if item.get(CONF_CLOSING_STATE_ADDRESS):
        return "closing"
    return "timed"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, _ = get_coordinator_and_device_info(entry)

    entities: list[S7Cover | S7PositionCover] = []

    for item in entry.options.get(CONF_COVERS, []):
        # Check if this is a position-based cover
        position_state = item.get(CONF_POSITION_STATE_ADDRESS)
        area = item.get(CONF_AREA)

        if position_state:
            # Position-based cover (0-100)
            position_command = item.get(CONF_POSITION_COMMAND_ADDRESS)
            scan_interval = item.get(CONF_SCAN_INTERVAL)
            invert_position = item.get(CONF_INVERT_POSITION, False)
            stop_command = item.get(CONF_STOP_COMMAND_ADDRESS)
            stop_pulse = item.get(CONF_STOP_PULSE_DURATION, DEFAULT_PULSE_DURATION)

            position_topic = f"cover:position:{position_state}"
            await coord.add_item(position_topic, position_state, scan_interval)

            # Optional: tilt control, symmetric to position above.
            tilt_state = item.get(CONF_TILT_STATE_ADDRESS)
            tilt_command = None
            if tilt_state:
                tilt_command = item.get(CONF_TILT_COMMAND_ADDRESS)
                tilt_topic = f"cover:tilt:{tilt_state}"
                await coord.add_item(tilt_topic, tilt_state, scan_interval)

            invert_tilt = item.get(CONF_INVERT_TILT, False)

            # Optional: real-time movement status, same climate-style single
            # status address + per-status value mapping as
            # hvac_status_address. Without it, is_opening/is_closing can
            # only ever be False here, since a raw position alone can't
            # tell HA whether the cover is actively moving.
            cover_status_address = item.get(CONF_COVER_STATUS_ADDRESS)
            cover_status_topic = None
            if cover_status_address:
                cover_status_topic = f"cover:status:{cover_status_address}"
                await coord.add_item(
                    cover_status_topic, cover_status_address, scan_interval
                )

            cover_status_open_values = item.get(
                CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES
            )
            cover_status_closed_values = item.get(
                CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES
            )
            cover_status_opening_values = item.get(
                CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES
            )
            cover_status_closing_values = item.get(
                CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES
            )
            cover_status_stopped_values = item.get(
                CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES
            )

            name = item.get(CONF_NAME) or default_entity_name(position_state)
            unique_id = item[CONF_UID]
            device_class = item.get(CONF_DEVICE_CLASS)

            entities.append(
                S7PositionCover(
                    coord,
                    name,
                    unique_id,
                    device_info,
                    position_state,
                    position_command,
                    invert_position,
                    device_class,
                    area,
                    stop_command,
                    stop_pulse,
                    tilt_state_address=tilt_state,
                    tilt_command_address=tilt_command,
                    invert_tilt=invert_tilt,
                    cover_status_topic=cover_status_topic,
                    cover_status_address=cover_status_address,
                    cover_status_open_values=cover_status_open_values,
                    cover_status_closed_values=cover_status_closed_values,
                    cover_status_opening_values=cover_status_opening_values,
                    cover_status_closing_values=cover_status_closing_values,
                    cover_status_stopped_values=cover_status_stopped_values,
                )
            )
            continue

        # Traditional open/close cover.
        open_command = item.get(CONF_OPEN_COMMAND_ADDRESS)
        close_command = item.get(CONF_CLOSE_COMMAND_ADDRESS)
        toggle_mode = bool(item.get(CONF_TOGGLE_MODE, DEFAULT_TOGGLE_MODE))
        toggle_pulse_duration = item.get(
            CONF_TOGGLE_PULSE_DURATION, DEFAULT_PULSE_DURATION
        )

        if not open_command:
            _LOGGER.debug("Skipping cover with missing open command address")
            continue

        if not close_command and not toggle_mode:
            _LOGGER.debug("Skipping cover with missing close command address")
            continue

        feedback_mode = _traditional_feedback_mode(item)
        # Only feedback belonging to the selected mode may affect the entity.
        opened_state = (
            item.get(CONF_OPENING_STATE_ADDRESS)
            if feedback_mode in {"opening", "both"}
            else None
        )
        closed_state = (
            item.get(CONF_CLOSING_STATE_ADDRESS)
            if feedback_mode in {"closing", "both"}
            else None
        )
        scan_interval = item.get(CONF_SCAN_INTERVAL)

        opened_topic = None
        closed_topic = None

        if opened_state:
            opened_topic = f"cover:opened:{opened_state}"
            await coord.add_item(opened_topic, opened_state, scan_interval)

        if closed_state:
            closed_topic = f"cover:closed:{closed_state}"
            await coord.add_item(closed_topic, closed_state, scan_interval)

        # Optional: real-time movement status, read independently of the
        # opened/closed end-stops above and of position feedback - each is a
        # separate boolean address, not a multi-value status word. The user
        # decides which sources to wire up, so a status word chosen for
        # position feedback does not silently discard separately configured
        # movement bits (or vice versa); see _toggle_movement/_toggle_position
        # for how S7Cover composes both independently in toggle_mode.
        cover_opening_address = item.get(CONF_COVER_OPENING_ADDRESS)
        cover_closing_address = item.get(CONF_COVER_CLOSING_ADDRESS)
        cover_stopped_address = item.get(CONF_COVER_STOPPED_ADDRESS)

        cover_opening_topic = None
        cover_closing_topic = None
        cover_stopped_topic = None

        if cover_opening_address:
            cover_opening_topic = f"cover:opening:{cover_opening_address}"
            await coord.add_item(
                cover_opening_topic, cover_opening_address, scan_interval
            )

        if cover_closing_address:
            cover_closing_topic = f"cover:closing:{cover_closing_address}"
            await coord.add_item(
                cover_closing_topic, cover_closing_address, scan_interval
            )

        if cover_stopped_address:
            cover_stopped_topic = f"cover:stopped:{cover_stopped_address}"
            await coord.add_item(
                cover_stopped_topic, cover_stopped_address, scan_interval
            )

        # Optional alternative to the 3 boolean addresses above: a single
        # climate-style status address + per-status value mapping, same as
        # the Position cover's cover_status_address. Takes priority over
        # the boolean addresses when configured.
        cover_status_address = item.get(CONF_COVER_STATUS_ADDRESS)
        cover_status_topic = None
        if cover_status_address:
            cover_status_topic = f"cover:status:{cover_status_address}"
            await coord.add_item(
                cover_status_topic, cover_status_address, scan_interval
            )

        cover_status_open_values = item.get(
            CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES
        )
        cover_status_closed_values = item.get(
            CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES
        )
        cover_status_opening_values = item.get(
            CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES
        )
        cover_status_closing_values = item.get(
            CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES
        )
        cover_status_stopped_values = item.get(
            CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES
        )

        name = item.get(CONF_NAME) or default_entity_name(open_command)
        unique_id = item[CONF_UID]
        device_class = item.get(CONF_DEVICE_CLASS)

        raw_operate_time = item.get(CONF_OPERATE_TIME, DEFAULT_OPERATE_TIME)
        try:
            operate_time = float(raw_operate_time)
        except (TypeError, ValueError):
            operate_time = float(DEFAULT_OPERATE_TIME)
        else:
            if operate_time < 0:
                operate_time = float(DEFAULT_OPERATE_TIME)

        use_state_topics = feedback_mode in {"opening", "closing", "both"}

        entities.append(
            S7Cover(
                coord,
                name,
                unique_id,
                device_info,
                open_command,
                close_command,
                opened_state,
                closed_state,
                opened_topic,
                closed_topic,
                operate_time,
                use_state_topics,
                device_class,
                area,
                feedback_mode=feedback_mode,
                cover_opening_address=cover_opening_address,
                cover_closing_address=cover_closing_address,
                cover_stopped_address=cover_stopped_address,
                cover_opening_topic=cover_opening_topic,
                cover_closing_topic=cover_closing_topic,
                cover_stopped_topic=cover_stopped_topic,
                cover_status_topic=cover_status_topic,
                cover_status_address=cover_status_address,
                cover_status_open_values=cover_status_open_values,
                cover_status_closed_values=cover_status_closed_values,
                cover_status_opening_values=cover_status_opening_values,
                cover_status_closing_values=cover_status_closing_values,
                cover_status_stopped_values=cover_status_stopped_values,
                toggle_mode=toggle_mode,
                toggle_pulse_duration=toggle_pulse_duration,
            )
        )

    if entities:
        await async_configure_entity_availability(
            entities, entry.options.get(CONF_COVERS, [])
        )
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Cover(S7BaseEntity, CoverEntity):
    """Representation of an S7 cover entity."""

    _attr_assumed_state = True

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        open_command: str,
        close_command: str | None,
        opened_state: str | None,
        closed_state: str | None,
        opened_topic: str | None,
        closed_topic: str | None,
        operate_time: float,
        use_state_topics: bool,
        device_class: str | None = None,
        suggested_area_id: str | None = None,
        feedback_mode: str | None = None,
        cover_opening_address: str | None = None,
        cover_closing_address: str | None = None,
        cover_stopped_address: str | None = None,
        cover_opening_topic: str | None = None,
        cover_closing_topic: str | None = None,
        cover_stopped_topic: str | None = None,
        cover_status_topic: str | None = None,
        cover_status_address: str | None = None,
        cover_status_open_values: str = DEFAULT_COVER_STATUS_OPEN_VALUES,
        cover_status_closed_values: str = DEFAULT_COVER_STATUS_CLOSED_VALUES,
        cover_status_opening_values: str = DEFAULT_COVER_STATUS_OPENING_VALUES,
        cover_status_closing_values: str = DEFAULT_COVER_STATUS_CLOSING_VALUES,
        cover_status_stopped_values: str = DEFAULT_COVER_STATUS_STOPPED_VALUES,
        toggle_mode: bool = DEFAULT_TOGGLE_MODE,
        toggle_pulse_duration: float = DEFAULT_PULSE_DURATION,
    ) -> None:
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=cover_status_topic or opened_topic or closed_topic,
            suggested_area_id=suggested_area_id,
        )
        self._open_command_address = open_command
        self._close_command_address = close_command
        self._toggle_mode = toggle_mode
        self._toggle_pulse_duration = toggle_pulse_duration
        self._last_toggle_direction: str | None = None
        self._toggle_lock = asyncio.Lock()
        # Set while a halt pulse is waiting for real "stopped" feedback
        # before continuing toward the originally requested target - see
        # _toggle_step/_handle_coordinator_update.
        self._toggle_pending_goal: str | None = None
        # Bumped by every explicit open/close/stop call. A deferred
        # continuation captures the value at scheduling time and re-checks
        # it once it actually acquires the lock, so a newer explicit
        # command that arrives after the continuation was scheduled (but
        # before it ran) still supersedes it - closes the race window
        # between _toggle_pending_goal being cleared and the scheduled
        # task actually executing; see _toggle_press.
        self._toggle_command_generation = 0
        # Toggle mode still advertises the full OPEN|CLOSE|STOP set, same as
        # a normal cover - Home Assistant's service layer checks
        # supported_features before ever calling async_open_cover/
        # async_close_cover/async_stop_cover, so advertising only OPEN would
        # make HA silently reject close_cover/stop_cover/toggle calls before
        # they reach this entity at all. Each of the three methods below
        # translates its own request into the correct physical press (or a
        # no-op/refusal) for the single-button relay - see _toggle_press.
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        self._opened_state_address = opened_state  # Finecorsa aperto
        self._closed_state_address = closed_state  # Finecorsa chiuso
        self._opened_topic = opened_topic
        self._closed_topic = closed_topic
        self._operate_time = max(float(operate_time), 0.0)
        self._use_state_topics = use_state_topics
        self._feedback_mode = feedback_mode or (
            "both"
            if use_state_topics
            else "status" if cover_status_address else "timed"
        )
        self._reset_handles: dict[str, Callable[[], None]] = {}
        self._is_opening = False
        self._is_closing = False
        self._ha_command_direction: str | None = None
        self._ha_movement_feedback_seen = False
        self._assumed_closed: bool = (
            False  # Assume open by default when using operate_time
        )
        # Optional real-time movement status: overrides the internal timer
        # flags above for display when configured. Independent of
        # is_closed, which always comes from opened_state/closed_state,
        # unless cover_status_address (below) matches open/closed.
        self._cover_opening_address = cover_opening_address
        self._cover_closing_address = cover_closing_address
        self._cover_stopped_address = cover_stopped_address
        self._cover_opening_topic = cover_opening_topic
        self._cover_closing_topic = cover_closing_topic
        self._cover_stopped_topic = cover_stopped_topic

        # Optional alternative to the 3 boolean addresses above: a single
        # climate-style status address + per-status value mapping (same
        # mechanism as the Position cover's cover_status_address), for PLCs
        # that expose movement as one status word instead of separate bits.
        # Takes priority over the boolean addresses when configured.
        self._cover_status_address = cover_status_address
        self._cover_status_topic = cover_status_topic
        self._cover_status_values: dict[str, list[int]] = {
            "open": parse_mode_values(cover_status_open_values),
            "closed": parse_mode_values(cover_status_closed_values),
            "opening": parse_mode_values(cover_status_opening_values),
            "closing": parse_mode_values(cover_status_closing_values),
            "stopped": parse_mode_values(cover_status_stopped_values),
        }
        if device_class:
            try:
                self._attr_device_class = CoverDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    def _get_topic_state(self, topic: str | None) -> bool | None:
        if topic is None:
            return None
        data = self.coordinator.data or {}
        if topic not in data:
            return None
        value = data.get(topic)
        if value is None:
            return None
        return bool(value)

    def _get_movement_status(self) -> str | None:
        """Return "open"/"closed"/"opening"/"closing"/"stopped", or None if
        unmatched/unset."""
        if not self._cover_status_address:
            return None
        data = self.coordinator.data or {}
        status = data.get(self._cover_status_topic)
        if status is None:
            return None
        try:
            status = int(status)
        except (TypeError, ValueError):
            return None
        for movement, values in self._cover_status_values.items():
            if status in values:
                return movement
        return None

    def _get_feedback_movement(self) -> str | None:
        """Return movement reported by configured PLC feedback."""
        if self._cover_status_address:
            status_movement = self._get_movement_status()
            if status_movement is not None:
                return status_movement
            if self._feedback_mode == "status":
                return None

        if self._cover_stopped_address and self._get_topic_state(
            self._cover_stopped_topic
        ):
            return "stopped"

        opening_state = (
            self._get_topic_state(self._cover_opening_topic)
            if self._cover_opening_address
            else None
        )
        closing_state = (
            self._get_topic_state(self._cover_closing_topic)
            if self._cover_closing_address
            else None
        )
        if opening_state is True and closing_state is True:
            return None
        if opening_state is True:
            return "opening"
        if closing_state is True:
            return "closing"
        if opening_state is not None or closing_state is not None:
            return "stopped"

        return None

    def _get_effective_movement(self) -> str | None:
        """Return movement from the highest-priority usable source."""
        feedback = self._get_feedback_movement()
        if feedback is not None:
            return feedback
        if self._feedback_mode == "status":
            # A selected status word is authoritative.  Missing/unknown data
            # must not silently fall back to command timers.
            return None

        if self._is_opening:
            return "opening"
        if self._is_closing:
            return "closing"
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        completion_direction = None

        # If using state topics (limit switches), check if movement should stop
        if self._use_state_topics:
            opened_state = self._get_topic_state(self._opened_topic)
            closed_state = self._get_topic_state(self._closed_topic)

            # If opening and reached open position, stop
            if self._ha_command_direction == "open" and opened_state is True:
                _LOGGER.debug("Cover %s reached open position, stopping", self.name)
                completion_direction = "open"

            # If closing and reached closed position, stop
            elif self._ha_command_direction == "close" and closed_state is True:
                _LOGGER.debug("Cover %s reached closed position, stopping", self.name)
                completion_direction = "close"

        if completion_direction is None and self._ha_command_direction is not None:
            feedback = self._get_feedback_movement()
            expected_feedback = (
                "opening" if self._ha_command_direction == "open" else "closing"
            )
            if feedback == expected_feedback:
                self._ha_movement_feedback_seen = True
            elif self._ha_movement_feedback_seen and feedback is not None:
                completion_direction = self._ha_command_direction

        if completion_direction is not None:
            self._ha_command_direction = None
            self._ha_movement_feedback_seen = False
            self.hass.async_create_task(self._complete_operation(completion_direction))

        # Remember the last real direction of travel so a subsequent
        # "stopped" reading knows which way another toggle press would
        # reverse to (see _toggle_state/_toggle_press). Must never be
        # cleared on "stopped" - it needs to survive the transition.
        if self._toggle_mode:
            state = self._toggle_state()
            if state in ("opening", "closing"):
                self._last_toggle_direction = state
            elif (
                state == "stopped"
                and self._toggle_pending_goal is not None
                and not self._toggle_lock.locked()
            ):
                # A halt pulse issued by _toggle_step is now confirmed by
                # real feedback - continue toward the originally requested
                # open/close target, fully feedback-driven (no fixed delay
                # between the two pulses). The lock check skips this while
                # the halt itself is still in flight; _toggle_step already
                # handles that case synchronously once its own pulse
                # completes.
                pending, self._toggle_pending_goal = self._toggle_pending_goal, None
                self.hass.async_create_task(
                    self._toggle_press(
                        pending,
                        expected_generation=self._toggle_command_generation,
                    )
                )

        super()._handle_coordinator_update()

    def _entity_data_available(self) -> bool:
        if self._feedback_mode == "status":
            topics = [self._cover_status_topic] if self._cover_status_topic else []
        elif self._feedback_mode in {"opening", "closing", "both"}:
            topics = [t for t in (self._opened_topic, self._closed_topic) if t]
        else:
            topics = []
        if not topics:
            return True
        data = self.coordinator.data or {}
        return all((topic in data and data[topic] is not None) for topic in topics)

    @property
    def is_opening(self) -> bool:
        """Return True when the effective movement is opening."""
        return self._get_effective_movement() == "opening"

    @property
    def is_closing(self) -> bool:
        """Return True when the effective movement is closing."""
        return self._get_effective_movement() == "closing"

    @property
    def is_closed(self) -> bool | None:
        if self._feedback_mode == "status" and self._cover_status_address:
            movement = self._get_movement_status()
            if movement == "closed":
                return True
            if movement == "open":
                return False
            return None
        if self._use_state_topics:
            # Use state topics for position feedback
            closed_state = self._get_topic_state(self._closed_topic)
            opened_state = self._get_topic_state(self._opened_topic)

            # Closed topic is True → cover is closed
            if closed_state is True and opened_state is not True:
                return True

            # Opened topic is True → cover is open (not closed)
            if opened_state is True and closed_state is not True:
                return False

            # Both are False or None → unknown state (cover is between positions)
            return None
        else:
            # Use operate time logic - assume cover reaches position after operate_time
            if self._is_opening:
                return False  # Opening, so not closed
            if self._is_closing:
                return False  # Closing but not yet closed
            # Return last known/assumed position
            return self._assumed_closed

    def _toggle_movement(self) -> str | None:
        """toggle_mode-only: "opening"/"closing"/"stopped", from whichever
        movement source is actually configured (status word if it has
        opening/closing/stopped values mapped, else the boolean bits),
        checked independently of the position feedback selector
        (_feedback_mode) below - the two are independently selectable in
        the config panel, so a status word mapped only for open/closed
        must not block a separately configured set of movement bits, and
        vice versa. Deliberately self-contained rather than reusing
        _get_feedback_movement()/_get_effective_movement(): those couple
        movement to _feedback_mode=="status" for the traditional-cover
        code path, which is exactly the coupling toggle_mode must not
        have. Returns None when no configured source produces a
        movement-specific reading."""
        if self._cover_status_address:
            status = self._get_movement_status()
            if status in ("opening", "closing", "stopped"):
                return status
        if self._cover_stopped_address and self._get_topic_state(
            self._cover_stopped_topic
        ):
            return "stopped"
        opening = (
            self._get_topic_state(self._cover_opening_topic)
            if self._cover_opening_address
            else None
        )
        closing = (
            self._get_topic_state(self._cover_closing_topic)
            if self._cover_closing_address
            else None
        )
        if opening is True and closing is True:
            return None
        if opening is True:
            return "opening"
        if closing is True:
            return "closing"
        if opening is not None or closing is not None:
            return "stopped"
        return None

    def _toggle_position(self) -> str | None:
        """toggle_mode-only: "open"/"closed", from whichever position
        feedback source is selected (_feedback_mode): the status word only
        when it's explicitly the chosen position source, otherwise the
        end-stops - independent of whatever movement source
        _toggle_movement() above resolves. Returns None when the selected
        source has no usable reading yet."""
        if self._feedback_mode == "status" and self._cover_status_address:
            status = self._get_movement_status()
            if status == "closed":
                return "closed"
            if status == "open":
                return "open"
            return None
        if self._use_state_topics:
            opened = self._get_topic_state(self._opened_topic)
            closed = self._get_topic_state(self._closed_topic)
            if closed is True and opened is not True:
                return "closed"
            if opened is True and closed is not True:
                return "open"
        return None

    def _toggle_state(self) -> str:
        """Effective toggle-cycle state: "closed"/"opening"/"open"/
        "closing"/"stopped", or "unknown". toggle_mode only.

        Composes the two independently configurable feedback sources -
        _toggle_movement() for opening/closing/stopped, _toggle_position()
        for open/closed - rather than assuming a single status word (or a
        single boolean setup) drives both. "unknown" means neither source
        has a usable reading yet (e.g. right after a Home Assistant
        restart, or an unmatched status value): it must stay distinct from
        a genuine "stopped" reading, since toggle_mode's command decisions
        depend entirely on knowing the real state - see _toggle_step.

        Movement wins when it reports actual motion (opening/closing),
        since that's the more specific/current reading. Otherwise a
        resolved position (open/closed) wins over a bare "stopped" from
        movement, since a settled endpoint is more informative than
        "stopped somewhere mid-travel".
        """
        movement = self._toggle_movement()
        if movement in ("opening", "closing"):
            return movement
        position = self._toggle_position()
        if position is not None:
            return position
        return "stopped" if movement == "stopped" else "unknown"

    async def _pulse_toggle(self) -> None:
        """Single-button mode: one pulse on open_command_address is all the
        PLC's step-by-step relay needs - it advances the physical cycle by
        itself. No local optimistic state to maintain beyond
        _last_toggle_direction (set by callers when the resulting direction
        is deterministically known)."""
        await self._ensure_connected()
        await self.coordinator.write_batched(self._open_command_address, True)
        await asyncio.sleep(self._toggle_pulse_duration)
        await self.coordinator.write_batched(self._open_command_address, False)
        await self.coordinator.async_request_refresh()

    async def _toggle_press(
        self, target: str, *, expected_generation: int | None = None
    ) -> None:
        """Entry point for a HA service call (target is "open"/"close"/
        "stop"): serializes against overlapping presses - including the
        automatic continuation _handle_coordinator_update may schedule -
        then delegates the actual decision to _toggle_step.

        expected_generation is set only by the deferred-continuation path
        in _handle_coordinator_update, which captures
        self._toggle_command_generation at scheduling time. Every explicit
        open/close/stop call bumps that counter first (see
        async_open_cover/async_close_cover/async_stop_cover), so if a newer
        explicit command arrived between scheduling and this call actually
        acquiring the lock, the generation check catches it and the stale
        continuation aborts without pressing - closing the race window
        where _toggle_pending_goal was already cleared before the
        continuation ran, so a plain "is there a pending goal" check
        wouldn't see it. Explicit calls never pass this, so they always
        run.
        """
        async with self._toggle_lock:
            if (
                expected_generation is not None
                and expected_generation != self._toggle_command_generation
            ):
                return
            await self._toggle_step(target)
        self.async_write_ha_state()

    async def _toggle_step(self, target: str) -> None:
        """Single-button mode: translate a request (target is "open"/
        "close"/"stop") into the correct physical press, or a no-op, for
        the single relay - never a blind alias. The physical cycle only
        ever advances one step per press (closed->opening->stopped->
        closing->stopped->opening->...), so a press can only reach a given
        target from specific states; see the module-level toggle_mode design
        note in const.py (CONF_TOGGLE_MODE) for the full state table.
        Must run under self._toggle_lock (see _toggle_press) - it recurses
        into itself directly (not through _toggle_press) when it can
        already confirm completion without waiting for another update.

        "stop" is always safe *by design*, but not by blindly trusting
        stale feedback: it always cancels any pending automatic
        continuation (an explicit stop means the user does not want the
        cover to keep moving toward a previously requested target), and if
        a halt pulse was already in flight for that continuation (pending
        goal was set), a fresh pulse is *not* sent even if the still-stale
        pre-halt reading says the cover is moving - that stale reading is
        exactly what the halt pulse was issued to correct, and pressing
        again on top of it could resume movement the halt already stopped.
        Only presses when the cover is moving *and* no halt is already in
        flight for it.

        "open"/"close" first cancel any previous pending continuation -
        every new explicit command represents the caller's latest desired
        target and must fully supersede whatever an earlier call queued,
        even if this new call turns out to be a no-op action-wise (e.g.
        the cover already happens to be moving the newly requested way).
        They then only press when the result is deterministic:
        - already at the goal (open/opening, or closed/closing respectively)
          -> no-op, never stop an already-correct movement just because the
          service was called again
        - settled at the opposite endpoint -> press (goes straight to the
          moving state that leads to the goal)
        - moving the wrong way -> press (halts it), then continue toward
          the goal automatically once real feedback confirms the halt
          succeeded ("stopped", not merely "unknown") - a single
          open_cover/close_cover call should eventually get the cover
          moving toward its target, not just stop it. If feedback isn't
          available immediately, the continuation is deferred and resumed
          by _handle_coordinator_update the next time real "stopped"
          feedback arrives - fully feedback-driven, no fixed delay between
          the two pulses.
        - stopped mid-travel -> press only if _last_toggle_direction says
          the next press reverses toward the goal; otherwise refuse and log
          a warning, since reaching the goal from here needs two more
          presses that first move the cover further the wrong way - not
          something to do silently.
        - state is "unknown" (no usable feedback yet, e.g. right after a HA
          restart, or an unmatched status value) -> refuse the same way;
          pressing blindly could visibly move the cover the wrong way
          first.
        """
        state = self._toggle_state()
        if target == "stop":
            had_pending_continuation = self._toggle_pending_goal is not None
            self._toggle_pending_goal = None
            if not had_pending_continuation and state in ("opening", "closing"):
                await self._pulse_toggle()
            return

        # A new explicit open/close request always supersedes whatever an
        # earlier call queued for later - see the docstring above.
        self._toggle_pending_goal = None

        goal_settled, goal_moving, opposite_settled, reverses_from = (
            ("open", "opening", "closed", "closing")
            if target == "open"
            else ("closed", "closing", "open", "opening")
        )
        if state in (goal_settled, goal_moving):
            return  # already achieving the goal - no-op
        if state == opposite_settled:
            await self._pulse_toggle()
            self._last_toggle_direction = goal_moving
            return
        if state == "stopped" and self._last_toggle_direction == reverses_from:
            await self._pulse_toggle()  # reverses toward the goal
            self._last_toggle_direction = goal_moving
            return
        if state == "stopped":
            _LOGGER.warning(
                "Cover %s: cannot %s from a stopped, direction-ambiguous"
                " state without first moving the wrong way - refusing to"
                " press. Wait for feedback or press again once the"
                " direction is known.",
                self.name,
                target,
            )
            return
        if state == "unknown":
            _LOGGER.warning(
                "Cover %s: cannot %s - no usable PLC feedback has been"
                " received yet - refusing to press. Wait for feedback"
                " before issuing the command again.",
                self.name,
                target,
            )
            return

        # Moving the wrong way: halt it, then continue toward the goal
        # once real "stopped" feedback confirms the halt succeeded.
        await self._pulse_toggle()
        if self._toggle_state() == "stopped":
            await self._toggle_step(target)
        else:
            self._toggle_pending_goal = target

    async def async_open_cover(self, **kwargs) -> None:
        if self._toggle_mode:
            self._toggle_command_generation += 1
            await self._toggle_press("open")
            return
        await self._ensure_connected()
        await self._stop_operation("close")
        await self.coordinator.write_batched(self._open_command_address, True)
        self._is_opening = True
        self._is_closing = False
        self._ha_command_direction = "open"
        self._ha_movement_feedback_seen = False
        if not self._use_state_topics:
            self._assumed_closed = False  # Assume open when opening starts
        self._schedule_reset("open")
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs) -> None:
        if self._toggle_mode:
            self._toggle_command_generation += 1
            await self._toggle_press("close")
            return
        await self._ensure_connected()
        await self._stop_operation("open")
        await self.coordinator.write_batched(self._close_command_address, True)
        self._is_opening = False
        self._is_closing = True
        self._ha_command_direction = "close"
        self._ha_movement_feedback_seen = False
        if not self._use_state_topics:
            self._assumed_closed = True  # Assume closed when closing starts
        self._schedule_reset("close")
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover movement."""
        if self._toggle_mode:
            self._toggle_command_generation += 1
            await self._toggle_press("stop")
            return
        await self._ensure_connected()

        await self._stop_operation("open")
        await self._stop_operation("close")
        self._is_opening = False
        self._is_closing = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._open_command_address:
            attrs["s7_open_command_address"] = self._open_command_address.upper()
        if self._close_command_address:
            attrs["s7_close_command_address"] = self._close_command_address.upper()
        if self._use_state_topics:
            if self._opened_state_address:
                attrs["s7_opened_state_address"] = self._opened_state_address.upper()
            if self._closed_state_address:
                attrs["s7_closed_state_address"] = self._closed_state_address.upper()
            attrs["state_topics_used"] = True
        else:
            attrs["state_topics_used"] = False
        if self._opened_topic:
            interval = self.coordinator.get_scan_interval(self._opened_topic)
            attrs["opened_scan_interval"] = f"{interval} s"
        if self._closed_topic:
            interval = self.coordinator.get_scan_interval(self._closed_topic)
            attrs["closed_scan_interval"] = f"{interval} s"
        attrs["operate_time"] = f"{self._operate_time:.1f} s"
        attrs["cover_type"] = "open/close"
        if self._cover_opening_address:
            attrs["s7_cover_opening_address"] = self._cover_opening_address.upper()
        if self._cover_closing_address:
            attrs["s7_cover_closing_address"] = self._cover_closing_address.upper()
        if self._cover_stopped_address:
            attrs["s7_cover_stopped_address"] = self._cover_stopped_address.upper()
        if self._cover_status_address:
            attrs["s7_cover_status_address"] = self._cover_status_address.upper()
            attrs["s7_cover_status_values"] = self._cover_status_values
        attrs["toggle_mode"] = self._toggle_mode
        if self._toggle_mode:
            attrs["s7_toggle_last_direction"] = self._last_toggle_direction or "unknown"

        return attrs

    def _cancel_reset(self, direction: str) -> None:
        handle = self._reset_handles.pop(direction, None)
        if handle:
            handle()

    def _schedule_reset(self, direction: str) -> None:
        self._cancel_reset(direction)

        async def _async_reset() -> None:
            await self._complete_operation(direction)

        if self._operate_time <= 0:
            self.hass.async_create_task(_async_reset())
            return

        @callback
        def _callback(_now) -> None:
            self._reset_handles.pop(direction, None)
            self.hass.async_create_task(_async_reset())

        self._reset_handles[direction] = async_call_later(
            self.hass, self._operate_time, _callback
        )

    async def _stop_operation(self, direction: str) -> None:
        self._cancel_reset(direction)
        address = (
            self._open_command_address
            if direction == "open"
            else self._close_command_address
        )
        success = True
        if address:
            try:
                await self.coordinator.write_batched(address, False)
            except HomeAssistantError:
                success = False

        if direction == "open":
            self._is_opening = False
        else:
            self._is_closing = False
        if self._ha_command_direction == direction:
            self._ha_command_direction = None
            self._ha_movement_feedback_seen = False

        # When stopped, maintain last known position
        # No change to _assumed_closed - it keeps the last state

        self.async_write_ha_state()
        if not success:
            await self.coordinator.async_request_refresh()

    async def _complete_operation(self, direction: str) -> None:
        self._cancel_reset(direction)
        if self._ha_command_direction == direction:
            self._ha_command_direction = None
            self._ha_movement_feedback_seen = False
        address = (
            self._open_command_address
            if direction == "open"
            else self._close_command_address
        )
        if address:
            try:
                await self.coordinator.write_batched(address, False)
            except HomeAssistantError:
                pass  # Non-critical, already logged
        self._is_opening = False
        self._is_closing = False

        # _assumed_closed is already set when operation starts

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        for cancel in list(self._reset_handles.values()):
            cancel()
        self._reset_handles.clear()
        await super().async_will_remove_from_hass()


class S7PositionCover(S7BaseEntity, CoverEntity):
    """Representation of an S7 cover with position control (0-100).

    Optionally also supports tilt control (current_cover_tilt_position,
    open/close/set/stop_cover_tilt) when tilt_state_address is configured,
    symmetric to the position control above.
    """

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        position_state: str,
        position_command: str | None,
        invert_position: bool = False,
        device_class: str | None = None,
        suggested_area_id: str | None = None,
        stop_command: str | None = None,
        stop_pulse_duration: float = DEFAULT_PULSE_DURATION,
        tilt_state_address: str | None = None,
        tilt_command_address: str | None = None,
        invert_tilt: bool = False,
        cover_status_topic: str | None = None,
        cover_status_address: str | None = None,
        cover_status_open_values: str = DEFAULT_COVER_STATUS_OPEN_VALUES,
        cover_status_closed_values: str = DEFAULT_COVER_STATUS_CLOSED_VALUES,
        cover_status_opening_values: str = DEFAULT_COVER_STATUS_OPENING_VALUES,
        cover_status_closing_values: str = DEFAULT_COVER_STATUS_CLOSING_VALUES,
        cover_status_stopped_values: str = DEFAULT_COVER_STATUS_STOPPED_VALUES,
    ) -> None:
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=f"cover:position:{position_state}",
            suggested_area_id=suggested_area_id,
        )
        self._position_state_address = position_state
        self._position_command_address = position_command or position_state
        self._position_topic = f"cover:position:{position_state}"
        self._invert_position = invert_position
        self._stop_command_address = stop_command
        self._stop_pulse_duration = float(stop_pulse_duration)

        self._tilt_state_address = tilt_state_address
        self._tilt_command_address = tilt_command_address or tilt_state_address
        self._tilt_topic = (
            f"cover:tilt:{tilt_state_address}" if tilt_state_address else None
        )
        self._invert_tilt = invert_tilt

        # Optional real-time movement status: a raw position alone can't
        # tell HA whether the cover is actively moving, so is_opening/
        # is_closing stay False unless this is configured.
        self._cover_status_address = cover_status_address
        self._cover_status_topic = cover_status_topic
        self._cover_status_values: dict[str, list[int]] = {
            "open": parse_mode_values(cover_status_open_values),
            "closed": parse_mode_values(cover_status_closed_values),
            "opening": parse_mode_values(cover_status_opening_values),
            "closing": parse_mode_values(cover_status_closing_values),
            "stopped": parse_mode_values(cover_status_stopped_values),
        }

        features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        if tilt_state_address:
            features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
                | CoverEntityFeature.STOP_TILT
            )
        self._attr_supported_features = features

        if device_class:
            try:
                self._attr_device_class = CoverDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    @staticmethod
    def _clamp_percent(value: Any, invert: bool) -> int | None:
        """Clamp to 0-100 and invert a raw PLC value.

        Shared by position and tilt, which both read/write a 0-100
        percentage with an optional invert flag.
        """
        try:
            pct = int(value)
        except (TypeError, ValueError):
            return None
        pct = max(0, min(100, pct))
        if invert:
            pct = 100 - pct
        return pct

    def _get_position_value(self) -> int | None:
        """Get the current position value from coordinator data."""
        data = self.coordinator.data or {}
        if self._position_topic not in data:
            return None
        value = data.get(self._position_topic)
        if value is None:
            return None
        return self._clamp_percent(value, self._invert_position)

    def _get_tilt_value(self) -> int | None:
        """Get the current tilt value from coordinator data."""
        if self._tilt_topic is None:
            return None
        data = self.coordinator.data or {}
        if self._tilt_topic not in data:
            return None
        value = data.get(self._tilt_topic)
        if value is None:
            return None
        return self._clamp_percent(value, self._invert_tilt)

    def _entity_data_available(self) -> bool:
        data = self.coordinator.data or {}
        return self._position_topic in data and data[self._position_topic] is not None

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=open)."""
        return self._get_position_value()

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return current tilt position (0=closed, 100=open), if configured."""
        return self._get_tilt_value()

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed.

        If cover_status_address is configured and the status matches
        cover_status_open_values/cover_status_closed_values, that's
        authoritative. Otherwise (unconfigured, or the status currently
        reads "opening"/"closing"/"stopped"/unmatched) falls back to the
        position value (closed when position == 0).
        """
        if self._cover_status_address:
            movement = self._get_movement_status()
            if movement == "closed":
                return True
            if movement == "open":
                return False
        pos = self._get_position_value()
        if pos is None:
            return None
        return pos == 0

    def _get_movement_status(self) -> str | None:
        """Return "open"/"closed"/"opening"/"closing"/"stopped", or None if
        unmatched/unset."""
        if not self._cover_status_address:
            return None
        data = self.coordinator.data or {}
        status = data.get(self._cover_status_topic)
        if status is None:
            return None
        try:
            status = int(status)
        except (TypeError, ValueError):
            return None
        for movement, values in self._cover_status_values.items():
            if status in values:
                return movement
        return None

    @property
    def is_opening(self) -> bool:
        """Return True when cover_status_address reports "opening".

        Without cover_status_address, position alone can't distinguish
        "moving" from "stopped mid-travel", so this stays False.
        """
        if self._cover_status_address:
            return self._get_movement_status() == "opening"
        return False

    @property
    def is_closing(self) -> bool:
        """Return True when cover_status_address reports "closing". See
        is_opening."""
        if self._cover_status_address:
            return self._get_movement_status() == "closing"
        return False

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover (set position to 100)."""
        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover (set position to 0)."""
        await self.async_set_cover_position(position=0)

    async def async_set_cover_position(self, **kwargs) -> None:
        """Set cover position (0-100)."""
        await self._ensure_connected()

        position = kwargs.get("position")
        if position is None:
            _LOGGER.error("No position provided for set_cover_position")
            return

        # Clamp to 0-100
        position = max(0, min(100, int(position)))

        # Invert if needed: when user wants 0=open/100=closed,
        # we need to write the inverted value to the PLC
        plc_value = (100 - position) if self._invert_position else position

        await self.coordinator.write_batched(self._position_command_address, plc_value)

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover.

        If a stop command address is configured, pulse it for the configured
        duration.  Otherwise fall back to writing the current position back
        to the command address.
        """
        await self._ensure_connected()

        if self._stop_command_address:
            # Pulse the stop address: set True, wait, set False
            await self.coordinator.write_batched(self._stop_command_address, True)
            await asyncio.sleep(self._stop_pulse_duration)
            await self.coordinator.write_batched(self._stop_command_address, False)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            actual_position = self._get_position_value()
            if actual_position is not None:
                await self.coordinator.write_batched(
                    self._position_command_address, actual_position
                )
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
            else:
                cover_name = self._attr_name or self.unique_id
                _LOGGER.error(
                    "Cannot stop cover %s because current position is unknown",
                    cover_name,
                )

    async def async_open_cover_tilt(self, **kwargs) -> None:
        """Open the tilt (set tilt position to 100)."""
        await self.async_set_cover_tilt_position(tilt_position=100)

    async def async_close_cover_tilt(self, **kwargs) -> None:
        """Close the tilt (set tilt position to 0)."""
        await self.async_set_cover_tilt_position(tilt_position=0)

    async def async_set_cover_tilt_position(self, **kwargs) -> None:
        """Set tilt position (0-100)."""
        if not self._tilt_command_address:
            _LOGGER.error("Tilt is not configured for this cover")
            return
        await self._ensure_connected()

        tilt_position = kwargs.get("tilt_position")
        if tilt_position is None:
            _LOGGER.error("No tilt_position provided for set_cover_tilt_position")
            return

        tilt_position = max(0, min(100, int(tilt_position)))
        plc_value = (100 - tilt_position) if self._invert_tilt else tilt_position

        await self.coordinator.write_batched(self._tilt_command_address, plc_value)

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover_tilt(self, **kwargs) -> None:
        """Stop the tilt.

        Tilt and lift share the same physical stop output (one motor per
        cover), so this reuses stop_command_address exactly like
        async_stop_cover. Without one, falls back to writing the current
        tilt position back, same trick async_stop_cover uses for position.
        """
        if not self._tilt_command_address:
            _LOGGER.error("Tilt is not configured for this cover")
            return
        await self._ensure_connected()

        if self._stop_command_address:
            await self.coordinator.write_batched(self._stop_command_address, True)
            await asyncio.sleep(self._stop_pulse_duration)
            await self.coordinator.write_batched(self._stop_command_address, False)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            actual_tilt = self._get_tilt_value()
            if actual_tilt is not None:
                await self.async_set_cover_tilt_position(tilt_position=actual_tilt)
            else:
                cover_name = self._attr_name or self.unique_id
                _LOGGER.error(
                    "Cannot stop cover %s tilt because current tilt is unknown",
                    cover_name,
                )

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._position_state_address:
            attrs["s7_position_state_address"] = self._position_state_address.upper()
        if self._position_command_address:
            attrs["s7_position_command_address"] = (
                self._position_command_address.upper()
            )
        if self._stop_command_address:
            attrs["s7_stop_command_address"] = self._stop_command_address.upper()
            attrs["stop_pulse_duration"] = f"{self._stop_pulse_duration} s"
        if self._tilt_state_address:
            attrs["s7_tilt_state_address"] = self._tilt_state_address.upper()
        if self._tilt_command_address:
            attrs["s7_tilt_command_address"] = self._tilt_command_address.upper()
        if self._cover_status_address:
            attrs["s7_cover_status_address"] = self._cover_status_address.upper()
            attrs["s7_cover_status_values"] = self._cover_status_values
        interval = self.coordinator.get_scan_interval(self._position_topic)
        attrs["closed_scan_interval"] = f"{interval} s"
        attrs["cover_type"] = "position"
        return attrs
