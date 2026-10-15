import unittest

from force_brain import (
    Action,
    Enemy,
    Fighter,
    ForceClass,
    Snapshot,
    combo_for,
    decide,
    follow_distance,
    ComboStyle,
)


def quiet(**overrides) -> Snapshot:
    base = dict(
        me=Fighter(shifta=True, deband=True),
        partner=Fighter(shifta=True, deband=True),
        enemies=(Enemy(id=1, threat=10, defense_down=True, attack_down=True),),
        partner_has_aggro=True,
        in_bubble=True,
        flanking=True,
        has_drain_weapon=True,
        pp_ratio=1.0,
    )
    base.update(overrides)
    return Snapshot(**base)


class ForceBrainTest(unittest.TestCase):
    def test_paralysis_beats_a_combo(self):
        snap = quiet(partner=Fighter(hp_ratio=0.9, statuses=frozenset({"paralysis"}), shifta=True, deband=True))
        choice = decide(snap)
        self.assertEqual(choice.action, Action.ANTI)
        self.assertEqual(choice.target, "partner")

    def test_low_hp_beats_missing_buffs(self):
        snap = quiet(
            me=Fighter(hp_ratio=0.2, shifta=False, deband=False),
            partner=Fighter(hp_ratio=1.0, shifta=False, deband=False),
        )
        choice = decide(snap)
        self.assertEqual(choice.action, Action.RESTA)
        self.assertEqual(choice.target, "self")

    def test_partner_healed_before_self_at_the_same_hp(self):
        snap = quiet(
            me=Fighter(hp_ratio=0.3, shifta=True, deband=True),
            partner=Fighter(hp_ratio=0.3, shifta=True, deband=True),
        )
        choice = decide(snap)
        self.assertEqual(choice.target, "partner")

    def test_shifta_before_deband(self):
        snap = quiet(
            me=Fighter(shifta=False, deband=False),
            partner=Fighter(shifta=False, deband=False),
            enemies=(),
        )
        self.assertEqual(decide(snap).action, Action.SHIFTA)

    def test_zalure_on_the_toughest_target_in_a_new_room(self):
        snap = quiet(
            new_room=True,
            enemies=(
                Enemy(id=2, threat=3),
                Enemy(id=9, threat=40),
            ),
        )
        choice = decide(snap)
        self.assertEqual(choice.action, Action.ZALURE)
        self.assertEqual(choice.target, "enemy:9")

    def test_jellen_after_defense_is_already_down(self):
        snap = quiet(
            boss_present=True,
            enemies=(Enemy(id=1, threat=50, defense_down=True),),
        )
        self.assertEqual(decide(snap).action, Action.JELLEN)

    def test_whiff_aborts_into_a_backstep(self):
        snap = quiet(combo_whiffed=True)
        self.assertEqual(decide(snap).action, Action.DODGE_BACK)

    def test_low_pp_uses_the_drain_special(self):
        snap = quiet(pp_ratio=0.1)
        self.assertEqual(decide(snap).action, Action.DRAIN_SPECIAL)

    def test_fomar_casts_gi_once_it_is_safe_to_hit(self):
        choice = decide(quiet(), ForceClass.FOMAR)
        self.assertEqual(choice.action, Action.GI_TECH)
        self.assertEqual(combo_for(ForceClass.FOMAR), ComboStyle.NORMAL_HEAVY_HEAVY)
        self.assertLess(follow_distance(ForceClass.FOMAR), follow_distance(ForceClass.FONEWEARL))
        self.assertLess(follow_distance(ForceClass.FONEWEARL), follow_distance(ForceClass.FOMARL))

    def test_fonewearl_casts_from_behind_once_you_have_aggro(self):
        waiting = decide(quiet(partner_has_aggro=False, flanking=False))
        self.assertEqual(waiting.action, Action.HOLD_BUBBLE)
        fighting = decide(quiet(flanking=False))
        self.assertEqual(fighting.action, Action.OFFENSIVE_TECH)
        self.assertEqual(fighting.reason, "cast from the bubble")
        tapping = decide(quiet(pp_ratio=0.1, has_drain_weapon=False, flanking=False))
        self.assertEqual(tapping.action, Action.WEAPON_COMBO)
        self.assertEqual(tapping.reason, "pp tap")

    def test_fomarl_waits_for_aggro_then_uses_a_ranged_combo(self):
        waiting = decide(quiet(partner_has_aggro=False, flanking=False), ForceClass.FOMARL)
        self.assertEqual(waiting.action, Action.HOLD_BUBBLE)
        fighting = decide(quiet(), ForceClass.FOMARL)
        self.assertEqual(fighting.action, Action.WEAPON_COMBO)
        self.assertEqual(combo_for(ForceClass.FOMARL), ComboStyle.NORMAL_NORMAL_HEAVY)

    def test_poison_waits_until_hp_is_safe(self):
        dying = quiet(partner=Fighter(hp_ratio=0.2, statuses=frozenset({"poison"}), shifta=True, deband=True))
        self.assertEqual(decide(dying).action, Action.RESTA)
        stable = quiet(partner=Fighter(hp_ratio=0.8, statuses=frozenset({"poison"}), shifta=True, deband=True))
        self.assertEqual(decide(stable).action, Action.ANTI)


if __name__ == "__main__":
    unittest.main()
