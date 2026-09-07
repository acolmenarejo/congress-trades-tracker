import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Feed from "./pages/Feed";
import Ranking from "./pages/Ranking";
import MemberPage from "./pages/MemberPage";
import TickerPage from "./pages/TickerPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="feed" element={<Feed />} />
        <Route path="ranking" element={<Ranking />} />
        <Route path="members/:matchKey" element={<MemberPage />} />
        <Route path="tickers/:ticker" element={<TickerPage />} />
      </Route>
    </Routes>
  );
}

export default App;
