/**
 * サロン経営の効果音(ループしない短い音)。
 *
 * 音源は BGM と同じカタログ backend/gateway/data/bgm/catalog.json に scope "salon_se" で
 * 登録し、同じディレクトリに置く。ファイルが置かれていない音はカタログ API が返さないので、
 * 鳴らさない(1つも無ければ ♪ パネルに効果音の欄も出さない)。
 *
 *   salon_se_register  会計が確定したとき(レジの音)
 *   salon_se_ledger    開業・週の締めの演出で帳簿をめくる音
 *   salon_se_doorbell  開店のドアベル
 *
 * 再配布できない素材なので、音声ファイルはリポジトリに含めない(.gitignore)。開発者の手元に置き、
 * ポータブル版の zip にだけ同梱する。
 *
 * ON/OFF と音量は BGM とは別に持ち(localStorage salon_se_prefs)、初回はミュートにする。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchAdventureBgmCatalog } from "../apis/adventure";
import {
  type BgmPreferences,
  clamp01,
  loadBgmPreferences,
  saveBgmPreferences,
} from "../utils/bgmPreferences";

export type SalonSoundName = "register" | "ledger" | "doorbell";

const SOUND_KEYS: Record<SalonSoundName, string> = {
  register: "salon_se_register",
  ledger: "salon_se_ledger",
  doorbell: "salon_se_doorbell",
};

export interface SalonSoundEffects {
  /** 鳴らせる音が1つでもあるか */
  available: boolean;
  muted: boolean;
  /** 0.0〜1.0 */
  volume: number;
  setMuted: (muted: boolean) => void;
  setVolume: (volume: number) => void;
  /** 音を1回鳴らす。ミュート中・音源が無いときは何もしない */
  play: (name: SalonSoundName) => void;
}

/** enabled が false の間(サロン経営が OFF)はカタログを取りに行かない */
export function useSalonSoundEffects(enabled: boolean): SalonSoundEffects {
  const [urls, setUrls] = useState<Partial<Record<SalonSoundName, string>>>({});
  const [prefs, setPrefs] = useState<BgmPreferences>(() =>
    loadBgmPreferences("salon_se"),
  );
  const urlsRef = useRef(urls);
  urlsRef.current = urls;
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  const audioRef = useRef<Partial<Record<SalonSoundName, HTMLAudioElement>>>(
    {},
  );

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetchAdventureBgmCatalog()
      .then((catalog) => {
        if (cancelled) return;
        const found: Partial<Record<SalonSoundName, string>> = {};
        for (const [name, key] of Object.entries(SOUND_KEYS) as [
          SalonSoundName,
          string,
        ][]) {
          const track = catalog.tracks.find((item) => item.key === key);
          if (track) found[name] = track.url;
        }
        setUrls(found);
      })
      .catch(() => {
        // 効果音は飾りなので、カタログが取れなければ鳴らさないだけにする
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const sound = useCallback((name: SalonSoundName, volume: number) => {
    const url = urlsRef.current[name];
    if (!url || volume <= 0) return;
    let audio = audioRef.current[name];
    if (!audio) {
      audio = new Audio(url);
      audio.preload = "auto";
      audioRef.current[name] = audio;
    }
    audio.volume = volume;
    audio.currentTime = 0;
    // 自動再生の制限などで鳴らせなくても、画面の進行は妨げない
    audio.play().catch(() => {});
  }, []);

  const play = useCallback(
    (name: SalonSoundName) => {
      const { muted, volume } = prefsRef.current;
      if (!muted) sound(name, volume);
    },
    [sound],
  );

  const setMuted = useCallback(
    (muted: boolean) => {
      setPrefs((current) => {
        const next = { ...current, muted };
        saveBgmPreferences(next, "salon_se");
        return next;
      });
      // ON にしたときは、音量の目安になるよう鳴らせる音を1つ鳴らす
      if (!muted) {
        const sample = (Object.keys(SOUND_KEYS) as SalonSoundName[]).find(
          (name) => urlsRef.current[name],
        );
        if (sample) sound(sample, prefsRef.current.volume);
      }
    },
    [sound],
  );

  const setVolume = useCallback((volume: number) => {
    setPrefs((current) => {
      const next = { ...current, volume: clamp01(volume) };
      saveBgmPreferences(next, "salon_se");
      return next;
    });
  }, []);

  return useMemo(
    () => ({
      available: Object.keys(urls).length > 0,
      muted: prefs.muted,
      volume: prefs.volume,
      setMuted,
      setVolume,
      play,
    }),
    [urls, prefs, setMuted, setVolume, play],
  );
}
