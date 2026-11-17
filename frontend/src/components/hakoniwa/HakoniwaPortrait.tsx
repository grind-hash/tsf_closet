import { useTransparentImage } from "../../hooks/useTransparentImage";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らない)
const ALPHA_OPTIONS = { targetColor: null, threshold: 12, featherRadius: 1.8 };

interface HakoniwaPortraitProps {
  src: string | null;
  alt: string;
  className?: string;
}

/**
 * 住民の姿の小さな表示。白い背景の画像は透過してから出し、処理中・失敗時は元の画像を出す
 * (アルファを持つ画像はそのまま使われる)。
 */
export default function HakoniwaPortrait({
  src,
  alt,
  className,
}: HakoniwaPortraitProps) {
  const { url } = useTransparentImage(src, true, ALPHA_OPTIONS);
  if (!src) return null;
  return <img className={className} src={url ?? src} alt={alt} />;
}
