import { createBrowserRouter } from "react-router-dom";

import { RequireAuth } from "../components/RequireAuth";
import { AccountPage } from "../pages/AccountPage";
import { AdminPage } from "../pages/AdminPage";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { ProductDetailPage } from "../pages/ProductDetailPage";
import { SearchResultsPage } from "../pages/SearchResultsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <RequireAuth>
        <HomePage />
      </RequireAuth>
    ),
  },
  {
    path: "/search",
    element: (
      <RequireAuth>
        <SearchResultsPage />
      </RequireAuth>
    ),
  },
  {
    path: "/products/:productId",
    element: <ProductDetailPage />,
  },
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/account",
    element: (
      <RequireAuth>
        <AccountPage />
      </RequireAuth>
    ),
  },
  {
    path: "/admin",
    element: (
      <RequireAuth requireAdmin>
        <AdminPage />
      </RequireAuth>
    ),
  },
]);
