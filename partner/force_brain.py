"""Decision order for the Force partner.

The default partner is a FOnewearl: buffs and attack spells from behind the
HUcast. A weapon comes out only to recover Photon Points.

Emergency healing interrupts everything. After that: buffs, then debuffs,
then staying alive in the fight, then damage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ForceClass(Enum):
    FOMAR = "fomar"
    FOMARL = "fomarl"
    FONEWEARL = "fonewearl"


class Action(Enum):
    RESTA = "resta"
    ANTI = "anti"
    SHIFTA = "shifta"
    DEBAND = "deband"
    ZALURE = "zalure"
    JELLEN = "jellen"
    DODGE_BACK = "dodge_back"
    DRAIN_SPECIAL = "drain_special"
    WEAPON_COMBO = "weapon_combo"
    GI_TECH = "gi_tech"
    OFFENSIVE_TECH = "offensive_tech"
    FLANK = "flank"
    HOLD_BUBBLE = "hold_bubble"


class ComboStyle(Enum):
    NORMAL_HEAVY_HEAVY = "n-h-h"
    NORMAL_NORMAL_HEAVY = "n-n-h"


# Hard disable first. Poison and slow can wait behind a heal.
INTERRUPT_STATUSES = frozenset({"paralysis", "freeze", "shock", "confuse"})
DOT_STATUSES = frozenset({"poison"})

HP_INTERRUPT = 0.40
PP_DRAIN_AT = 0.25

# Game units, tuned once the client can measure a room.
# FOnewearl stands in closer than FOmarl so her buffs still reach the HUcast.
FOLLOW_DISTANCE = {
    ForceClass.FOMAR: 12.0,
    ForceClass.FONEWEARL: 20.0,
    ForceClass.FOMARL: 28.0,
}


@dataclass
class Fighter:
    hp_ratio: float = 1.0
    statuses: frozenset[str] = field(default_factory=frozenset)
    shifta: bool = False
    deband: bool = False


@dataclass
class Enemy:
    id: int
    threat: float
    defense_down: bool = False
    attack_down: bool = False


@dataclass
class Snapshot:
    me: Fighter
    partner: Fighter
    enemies: tuple[Enemy, ...] = ()
    new_room: bool = False
    boss_present: bool = False
    combo_whiffed: bool = False
    pp_ratio: float = 1.0
    has_drain_weapon: bool = False
    partner_has_aggro: bool = False
    in_bubble: bool = True
    flanking: bool = False


@dataclass
class Orders:
    """What you told me in chat. Healing still cuts ahead of these."""

    hold: bool = False
    distance_scale: float = 1.0
    resta: bool = False
    shifta: bool = False
    deband: bool = False


@dataclass(frozen=True)
class Decision:
    action: Action
    target: str
    reason: str


def _needs_heal(fighter: Fighter) -> bool:
    return fighter.hp_ratio < HP_INTERRUPT


def _interrupt_status(fighter: Fighter) -> str | None:
    for status in INTERRUPT_STATUSES:
        if status in fighter.statuses:
            return status
    return None


def _any_status(fighter: Fighter) -> str | None:
    hard = _interrupt_status(fighter)
    if hard:
        return hard
    for status in DOT_STATUSES:
        if status in fighter.statuses:
            return status
    return None


def _worse_hp(snap: Snapshot) -> tuple[str, Fighter]:
    if snap.partner.hp_ratio < snap.me.hp_ratio:
        return "partner", snap.partner
    if snap.me.hp_ratio < snap.partner.hp_ratio:
        return "self", snap.me
    if _needs_heal(snap.partner) or _needs_heal(snap.me):
        return "partner", snap.partner
    return "partner", snap.partner


def _toughest(enemies: tuple[Enemy, ...]) -> Enemy | None:
    if not enemies:
        return None
    return max(enemies, key=lambda enemy: enemy.threat)


def decide(
    snap: Snapshot,
    force: ForceClass = ForceClass.FONEWEARL,
    orders: Orders | None = None,
) -> Decision:
    """Pick the next action. Healing and hard status preempt buffs and combos."""

    for who, fighter in (("partner", snap.partner), ("self", snap.me)):
        status = _interrupt_status(fighter)
        if status:
            return Decision(Action.ANTI, who, f"{who} is {status}")

    who, fighter = _worse_hp(snap)
    if _needs_heal(fighter):
        return Decision(Action.RESTA, who, f"{who} hp {fighter.hp_ratio:.0%}")

    for who, fighter in (("partner", snap.partner), ("self", snap.me)):
        status = _any_status(fighter)
        if status:
            return Decision(Action.ANTI, who, f"{who} is {status}")

    if orders and orders.resta:
        return Decision(Action.RESTA, "partner", "you asked")
    if orders and orders.shifta:
        return Decision(Action.SHIFTA, "partner", "you asked")
    if orders and orders.deband:
        return Decision(Action.DEBAND, "partner", "you asked")

    if not snap.partner.shifta or not snap.me.shifta:
        target = "partner" if not snap.partner.shifta else "self"
        return Decision(Action.SHIFTA, target, "shifta down")
    if not snap.partner.deband or not snap.me.deband:
        target = "partner" if not snap.partner.deband else "self"
        return Decision(Action.DEBAND, target, "deband down")

    if orders and orders.hold:
        return Decision(Action.HOLD_BUBBLE, "partner", "you said hold")

    if snap.new_room or snap.boss_present:
        toughest = _toughest(snap.enemies)
        if toughest and not toughest.defense_down:
            return Decision(Action.ZALURE, f"enemy:{toughest.id}", "defense down")
        if toughest and not toughest.attack_down:
            return Decision(Action.JELLEN, f"enemy:{toughest.id}", "attack down")

    if snap.combo_whiffed:
        return Decision(Action.DODGE_BACK, "self", "attack whiffed")

    if snap.pp_ratio < PP_DRAIN_AT and snap.has_drain_weapon:
        return Decision(Action.DRAIN_SPECIAL, "enemy", "pp low")

    if not snap.in_bubble:
        return Decision(Action.HOLD_BUBBLE, "partner", "return to mid-range")

    if not snap.enemies:
        return Decision(Action.HOLD_BUBBLE, "partner", "stay behind partner")

    if not snap.partner_has_aggro:
        return Decision(Action.HOLD_BUBBLE, "partner", "wait for aggro")

    if force is ForceClass.FONEWEARL:
        if snap.pp_ratio >= PP_DRAIN_AT:
            return Decision(Action.OFFENSIVE_TECH, "enemy", "cast from the bubble")
        return Decision(Action.WEAPON_COMBO, "enemy", "pp tap")

    if not snap.flanking:
        return Decision(Action.FLANK, "enemy", "side or rear")

    if force is ForceClass.FOMAR and snap.pp_ratio >= PP_DRAIN_AT:
        return Decision(Action.GI_TECH, "enemy", "gizonde")

    return Decision(Action.WEAPON_COMBO, "enemy", combo_for(force).value)


def combo_for(force: ForceClass) -> ComboStyle:
    if force is ForceClass.FOMAR:
        return ComboStyle.NORMAL_HEAVY_HEAVY
    return ComboStyle.NORMAL_NORMAL_HEAVY


def follow_distance(force: ForceClass, orders: Orders | None = None) -> float:
    scale = 1.0 if orders is None else orders.distance_scale
    return FOLLOW_DISTANCE[force] * scale
