# Backend Modules

The backend is a modular monolith. Each module owns its domain behavior and
publishes a narrow `public.py` application surface plus versioned domain events.

The standard dependency direction is presentation -> application -> domain ->
ports, with infrastructure implementing the ports. Cross-module imports into
internal repositories or ORM mappings are prohibited.
