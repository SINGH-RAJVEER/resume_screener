"""Alembic entrypoint.

Alembic 1.19.1 generates operation wrappers by re-formatting function
signatures and stripping ``ForwardRef(...)`` wrappers with a regex. CPython
3.14 changed ``ForwardRef``'s repr to include an ``owner=`` argument, so the
regex no longer matches and the generated code fails to compile. Restoring
the pre-3.14 repr for this short-lived migration process keeps alembic
working unchanged.
"""

import typing

if hasattr(typing.ForwardRef, "__forward_arg__"):

	def _forward_ref_repr(self: typing.ForwardRef) -> str:
		return f"ForwardRef({self.__forward_arg__!r})"

	typing.ForwardRef.__repr__ = _forward_ref_repr

if __name__ == "__main__":
	from alembic.config import main

	main()
