# Composer mobile layout — contract

The composer (`app/src/components/dashboard/ChatInput.tsx` plus the controls under
`app/src/components/dashboard/chat/`) holds a small set of breakpoint rules. They are a
contract, not styling taste: below `lg` (1024px) the composer is expected to stay usable with a
thumb.

## Rules

| Rule | Where | Class |
|---|---|---|
| Interactive controls reach the 44px touch floor | action row | `max-lg:min-h-11` |
| Square icon buttons also keep the 44px width | plus, model chip, send/stop, mic | `max-lg:min-w-11` |
| The send button grows its padding instead of the desktop `min-h-9` | `ComposerSendButton` | `max-lg:p-3` |
| The action row reflows into a second line | `composer-actions-row` | `flex-wrap` |
| The row's inner gap widens | left control group | `max-lg:gap-2` |
| The command-palette button drops out | palette button | `max-sm:hidden` |
| The ask-mode hint drops out | `composer-ask-hint` | `hidden md:inline` |
| Composer menu rows reach the 44px floor | `ComposerMenu.MenuOptionRow` | `max-lg:min-h-11` |
| Long chip labels clamp narrower | model-chip label, permission badge | `max-lg:max-w-28`, `max-lg:max-w-20` |

Breakpoints are Tailwind defaults: `max-lg` is `< 1024px`, `max-sm` is `< 640px`, `md:` starts at
768px.

## Where this is held

- `app/src/components/dashboard/chat/composerMobile.test.tsx` (jsdom) asserts the class contract
  above — the cheapest run that fails when a floor is removed.
- `app/tests/playwright/composer-width.spec.ts` and
  `app/tests/playwright/mobile-viewport.spec.ts` measure the pixels (overlap, horizontal
  overflow) at 375/390px and on a narrowed desktop column.

## What this does not claim

- The jsdom file holds classes, not geometry. jsdom reports zero-sized rects, so a class that is
  present but overridden elsewhere still passes there; only the playwright lane sees the box.
- The menu-row floor is applied at `lg` and below for consistency with the controls, but the
  menus were only measured on a phone in an earlier audit, not re-shot in this lane.
