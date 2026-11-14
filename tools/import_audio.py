"""Copy the audio the game uses out of the downloaded packs into assets/audio/.

The full packs live in asset_packs/ (git-ignored, ~400 MB). The game only reads the small, tracked
copy in assets/audio/, under clean names. Add a line here when the game starts using a new sound,
then run:  python tools/import_audio.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "asset_packs"
OUT = ROOT / "assets" / "audio"

HORROR = "Horror SFX Free"  # by YourPalRob
DARKWORLD = "Darkworld Audio - Survival Effects [Free]"  # by Darkworld Audio
FILMCOW = "FilmCow Recorded SFX"  # by Jason Steele (FilmCow)
NIGHTMARE = "Lonely Nightmare/Lonely Nightmare/MP3"  # by Crow Shade
ABYSSAL = "Abyssal Horror SFX Vol.1/Abyssal Horror"  # by Riria/Ririsaurus (so are the next two)
BEASTS = "Beasts/Beasts"
MONSTERS = "Monsters SFX Vol.1/Monsters"
MONSTERS2 = "Monsters Vol.2/Monsters Vol.2"

# music name -> file inside asset_packs/
MUSIC = {
    "comfort": f"{NIGHTMARE}/Comfort.mp3",
    "a_place_ive_seen_before": f"{NIGHTMARE}/A Place I've Seen Before.mp3",
    "subtle_changes": f"{NIGHTMARE}/Subtle Changes.mp3",
    "lying_down": f"{NIGHTMARE}/Lying Down.mp3",
    "my_room": f"{NIGHTMARE}/My Room.mp3",
    "sealed": f"{NIGHTMARE}/Sealed.mp3",
    "ceiling_stars": f"{NIGHTMARE}/Ceiling Stars.mp3",
}

# sample key (see nightdrive/samples.py) -> file inside asset_packs/
SFX = {
    # jump-scare layers
    "metal_screech": f"{HORROR}/Ambient/Screech_metalic_dragging_3.wav",
    "laugh": f"{HORROR}/Monsters & Ghosts/Child laugh.wav",
    "drone": f"{HORROR}/Ambient/Drone_doom.wav",
    "ghost_scream": f"{HORROR}/Monsters & Ghosts/Ghost_scream_3.wav",
    "ghost_moan": f"{HORROR}/Monsters & Ghosts/Ghost_moan_2.wav",
    "thud": f"{DARKWORLD}/Combat/DesignedPunch3.wav",
    "car_crash": f"{DARKWORLD}/Destruction/DesignedCarCrash1.wav",
    "glass_smash": f"{DARKWORLD}/Destruction/LargeGlassMirrorSmash1.wav",
    "injured": f"{DARKWORLD}/Human/HumanInjured3.wav",
    "shriek_a": f"{MONSTERS}/Dinosaur_Shriek1.mp3",
    "shriek_b": f"{MONSTERS}/Dinosaur_Shriek10.mp3",
    "yeti_roar": f"{MONSTERS}/Monster_Roar14.mp3",
    "deep_froth": f"{ABYSSAL}/DeepOne_FrothyGrowl2.mp3",
    "deep_growl": f"{ABYSSAL}/DeepOne_Growl3.mp3",
    # creatures appearing
    "appear_deer": f"{HORROR}/Monsters & Ghosts/Monster_breath.wav",
    "appear_yeti": f"{BEASTS}/Beast_Sniff.wav",
    "appear_yeti_growl": f"{BEASTS}/Beast_Growl4.wav",
    "appear_deep_one": f"{ABYSSAL}/DeepOne_Grunt1.mp3",
    "twig": f"{DARKWORLD}/Destruction/WoodSnap2.wav",
    "snow_step": f"{DARKWORLD}/Footsteps/FootstepsSlushSnow3.wav",
    "wet_step": f"{DARKWORLD}/Footsteps/FootstepsWetGravelStones2.wav",
    # the player
    "gasp": f"{HORROR}/Character/Gasp_3.wav",
    "exhale": f"{DARKWORLD}/Human/HumanBreathingOut4.wav",
    "panic": f"{HORROR}/Character/Breathing_fast.wav",
    "laugh_kid": f"{HORROR}/Monsters & Ghosts/Child laugh_7.wav",
    # headlights
    "buzz": f"{HORROR}/House & Office/Fluorescent light bulb buzz_2.wav",
    **{
        f"switch_{state}_{i}": f"{DARKWORLD}/Environment/SwitchButton{i}_{state.capitalize()}.wav"
        for state in ("on", "off")
        for i in (1, 2, 3)
    },
    # the ghost (FilmCow): stinger, drone, rattles, creaks, knocks, footsteps in the dark, relief
    "ghost_stinger": f"{FILMCOW}/hit with melodic resonance 1.wav",
    "ghost_tone": f"{FILMCOW}/metal dinging underwater 9.wav",
    "ghost_rumble": f"{FILMCOW}/rumbling 4.wav",
    **{
        f"ghost_chain_{i}": f"{FILMCOW}/chain {n}.wav"
        for i, n in enumerate((9, 10, 11, 8), 1)
    },
    **{
        f"ghost_creak_{i}": f"{FILMCOW}/plastic siding strain {n}.wav"
        for i, n in enumerate((3, 9, 2), 1)
    },
    **{f"ghost_knock_{i}": f"{FILMCOW}/door knock {i}.wav" for i in (1, 2, 3)},
    **{f"ghost_step_{i}": f"{FILMCOW}/footstep leaves {i}.wav" for i in (1, 2, 3, 4)},
    "ghost_swoosh": f"{FILMCOW}/swoosh 8.wav",
    "scream_driver": f"{FILMCOW}/scream 2.wav",
    # replacing the old synthesised sounds
    "truck_horn": f"{HORROR}/Monsters & Ghosts/Robotic_bass.wav",  # a low buzzy blast
    "air_brake": f"{HORROR}/Character/Air Compressor Stopping.wav",
    "riser": f"{HORROR}/Stingers and Spooky Triggers/Slow Stinger.wav",  # only 3.0-4.5 s is used
    "shriek_c": f"{MONSTERS}/Dinosaur_Shriek5.mp3",  # a giant chicken
    "shriek_d": f"{MONSTERS}/Dinosaur_Shriek2.mp3",
    "phone_slam": f"{FILMCOW}/landline phone hang up angry 2.wav",  # "you're fired"
    "whistle_1": f"{FILMCOW}/slide whistle 7.wav",  # falling slide whistles: a sad trombone
    "whistle_2": f"{FILMCOW}/slide whistle 6.wav",
    "whistle_3": f"{FILMCOW}/slide whistle 2.wav",
    "whistle_4": f"{FILMCOW}/slide whistle 5.wav",
    "whistle_5": f"{FILMCOW}/slide whistle 16.wav",
    "bell_ding": f"{FILMCOW}/ding 3.wav",
    "bonk": f"{FILMCOW}/metal bonk distorted.wav",
    "squeak_a": f"{FILMCOW}/chair squeak 5.wav",
    "squeak_b": f"{FILMCOW}/chair squeak 8.wav",
    "switch_click": f"{FILMCOW}/light switch off.wav",
    "tv_zap": f"{FILMCOW}/tube tv turn off 4.wav",
    # the roadside monster and the hitchhikers
    "monster_growl": f"{MONSTERS}/Monster_SoftGrowl1.mp3",  # it appears
    "monster_attack": f"{MONSTERS2}/GreaWarg_Attack.wav",  # it saw you
    "monster_roar": f"{MONSTERS2}/Garmr_Growl.wav",
    "door_open": f"{FILMCOW}/car sedan door open 1.wav",  # picking someone up
    "door_shut": f"{FILMCOW}/car sedan door shut 1.wav",
    "laugh_spooky": f"{HORROR}/Monsters & Ghosts/Laugh_spooky_4.wav",  # the impostor
    # the car
    "engine": f"{FILMCOW}/ambience - car sedan inside.wav",
    # night ambience
    "frogs": f"{HORROR}/Ambient/Frogs_pitchshift.wav",
    "amb_yell": f"{HORROR}/Ambient/Distant Yell_Echo and Reverb_2.wav",
    "amb_bell": f"{HORROR}/Ambient/Bell_low.wav",
    "amb_creak": f"{HORROR}/Ambient/Mechanical Moan and Creaking.wav",
    "amb_crying": f"{HORROR}/Ambient/Crying_moaning_ambience_3.wav",
    "amb_tapping": f"{HORROR}/Ambient/Metal_tapping.wav",
    "amb_crows": f"{DARKWORLD}/Environment/BirdsCrowsDistantAmbienceLoop.wav",
    "amb_door": f"{DARKWORLD}/Environment/OldDoorCreak.wav",
    "amb_hoot": f"{BEASTS}/Beast_Hooting.wav",
    "amb_distant_roar": f"{MONSTERS}/Monster_Roar21.mp3",
    **{
        f"step_twig_{i}": f"{DARKWORLD}/Footsteps/FootstepsDryBeachTwigs{i}.wav"
        for i in (1, 2, 3, 4)
    },
}

# name in assets/audio/licenses/ -> file inside asset_packs/
LICENSES = {
    "lonely_nightmare_LICENSE.txt": "Lonely Nightmare/LICENSE.txt",
    "darkworld_audio_license.pdf": f"{DARKWORLD}/License Agreement.pdf",
    "ririsaurus_USAGE.txt": "Beasts/Ririsaurus_Asset_USAGE.txt",
    "filmcow_license.pdf": f"{FILMCOW}/license.pdf",
}


def copy_all():
    """Copy every listed file (keeping its extension) and delete stray ones. Returns missing sources."""
    missing = []
    jobs = (
        [
            (src, OUT / "music" / f"{name}{Path(src).suffix}")
            for name, src in MUSIC.items()
        ]
        + [
            (src, OUT / "sfx" / f"{name}{Path(src).suffix}")
            for name, src in SFX.items()
        ]
        + [(src, OUT / "licenses" / name) for name, src in LICENSES.items()]
    )
    wanted = set()
    for src, dest in jobs:
        source = PACKS / src
        if not source.exists():
            missing.append(src)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        wanted.add(dest)
    for folder in ("music", "sfx", "licenses"):  # remove what the game no longer uses
        for stray in (OUT / folder).glob("*"):
            if stray.is_file() and stray not in wanted:
                stray.unlink()
    return missing


if __name__ == "__main__":
    missing = copy_all()
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"copied into {OUT.relative_to(ROOT)}: {total / 1e6:.0f} MB")
    for src in missing:
        print(f"MISSING in asset_packs/: {src}")
    sys.exit(1 if missing else 0)
