import { useRef } from 'react';
import type { Character } from '../types';
import './CharacterSelect.css';

interface CharacterSelectProps {
  characters: Character[];
  onSelectCharacter: (characterId: string) => void;
  onCustomImage: (imageBase64: string) => void;
  isLoading: boolean;
}

export default function CharacterSelect({
  characters,
  onSelectCharacter,
  onCustomImage,
  isLoading,
}: CharacterSelectProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1];
      onCustomImage(base64);
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="character-select">
      <header className="header">
        <h1>✨ わくわくへんしんマジック！✨</h1>
        <p className="subtitle">
          すきなキャラクターをえらんで、いろんなすがたにへんしんしよう！
        </p>
      </header>

      <section className="transform-categories">
        <h2>🌟 へんしんできるすがたの例</h2>
        <div className="category-badges">
          <span className="badge hero">🦸 ヒーロー</span>
          <span className="badge wizard">🧙 まほうつかい</span>
          <span className="badge ninja">🥷 にんじゃ</span>
          <span className="badge space">🚀 うちゅうひこうし</span>
          <span className="badge princess">👸 おひめさま</span>
          <span className="badge fairy">🧚 ようせい</span>
          <span className="badge idol">🎀 アイドル</span>
          <span className="badge magicalgirl">🌸 まほうしょうじょ</span>
          <span className="badge adventure">🗺️ ぼうけんか</span>
          <span className="badge animal">🐱 どうぶつ</span>
        </div>
      </section>

      <section className="character-list">
        <h2>🎭 キャラクターをえらぼう</h2>
        <div className="character-grid">
          {characters.map((char) => (
            <button
              key={char.id}
              className="character-card"
              onClick={() => onSelectCharacter(char.id)}
              disabled={isLoading}
            >
              <img
                src={`data:image/png;base64,${char.thumbnail}`}
                alt={char.name}
                className="character-thumbnail"
              />
              <span className="character-name">{char.name}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="custom-upload">
        <h2>📷 じぶんのしゃしんをつかう</h2>
        <p>しゃしんをアップロードすると、アニメふうのキャラクターになるよ！</p>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          className="file-input"
        />
        <button
          className="upload-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
        >
          🖼️ しゃしんをえらぶ
        </button>
      </section>
    </div>
  );
}
