import { useLocation } from "react-router-dom";
import CharacterChatHub from "./CharacterChatHub";
import CharacterChatRoom from "./CharacterChatRoom";
import "./CharacterChatScreen.css";

// /talk（Hub）と /talk/:threadId（Room）を切り替える入口。

export default function CharacterChatScreen() {
  const location = useLocation();
  const threadId = location.pathname.split("/")[2];
  return threadId ? (
    <CharacterChatRoom threadId={threadId} />
  ) : (
    <CharacterChatHub />
  );
}
