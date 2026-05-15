import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE_NAME } from "@/lib/constants";

const PUBLIC_ROUTES = ["/login", "/register"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;

  // Протухший cookie: очищаем через Set-Cookie и редиректим на чистый /login
  if (pathname === "/login" && request.nextUrl.searchParams.get("expired") === "1") {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.delete(AUTH_COOKIE_NAME);
    return response;
  }

  const isPublicRoute = PUBLIC_ROUTES.some(
    (r) => pathname === r || pathname.startsWith(r + "/"),
  );

  // Не авторизован → редирект на /login с сохранением целевого пути
  if (!token && !isPublicRoute) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Уже авторизован, зашёл на публичный маршрут → на главную
  if (token && isPublicRoute) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Все маршруты, кроме _next internals и статических файлов с расширением
    "/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)",
  ],
};
