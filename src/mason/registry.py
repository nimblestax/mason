"""Every Rule Mason reports, and what its docs page says about it.

The reference pages are generated from here, so a Rule and its explanation can't drift apart.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principle:
    """A principle of the Nimblestax Way, published at nimblestax.com/way/<slug>."""

    title: str
    slug: str


@dataclass(frozen=True)
class Example:
    """Something that fails the Rule: files written into the project `mason init` creates, or a
    command run in it. `when` says what else must be true, for a failure no file can cause."""

    files: dict[str, str] = field(default_factory=dict)
    command: str = ""
    when: str = ""


@dataclass(frozen=True)
class Rule:
    name: str
    checks: str
    why: str
    example: Example
    fix: str
    principle: Principle | None = None


EVERY_CATALOG_IS_ONE_DOMAIN = Principle(
    "Every catalog is one domain in one environment", "every-catalog-is-one-domain"
)
DATA_FLOWS_ONE_WAY = Principle("Data flows one way", "data-flows-one-way")
SILVER_IS_TYPED = Principle(
    "Silver is typed, deduplicated and conformed", "silver-is-typed-and-conformed"
)
EXPECTATIONS_GUARD_ROWS = Principle(
    "Expectations guard rows; tests guard datasets", "expectations-guard-rows"
)
EVERY_CHANGE_IS_REVIEWED = Principle(
    "Every change goes through a pull request", "every-change-goes-through-a-pull-request"
)

ORDERS = "domains/sales/sources/orders.yaml"
LANDED_AS_JSON = (
    "kind: source\nversion: 1\npath: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
)
COUNTRIES = "domains/sales/seeds/countries.yaml"
COUNTRIES_CSV = "domains/sales/seeds/countries.csv"
FCT_ORDERS = "domains/sales/models/fct_orders.sql"
RECOVERY_GUIDE = "[Recover from a failed refresh](../../guides/recover-from-a-failed-refresh.md)"
COUNTRIES_CONFIG = "kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  code: STRING\n"

# Append only. An ID never changes meaning, and a retired rule stays here so its ID isn't reused.
RULES = {
    "MSN101": Rule(
        "missing-kind",
        checks="A config file has no `kind`.",
        why="`kind` says what a file declares, such as a Source or a Gold Model, and so which"
        " fields it may have. Without it, Mason can't check the rest of the file.",
        example=Example(
            {ORDERS: "version: 1\npath: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"}
        ),
        fix="Add `kind` at the top of the file, naming the Kind its folder holds: `source` in"
        " `sources/`, `seed` in `seeds/` and `model` in `models/`.",
    ),
    "MSN102": Rule(
        "unknown-kind",
        checks="A `kind` isn't one Mason knows.",
        why="Mason checks each file against its Kind's schema. A misspelt `kind` has no schema,"
        " so nothing in the file can be checked. `mason schema` reports this Rule too when it's"
        " asked for a Kind that doesn't exist, and exits 2, because the mistake is on the"
        " command line.",
        example=Example(
            {
                ORDERS: "kind: sauce\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Use one of the Kinds: `model`, `platform`, `seed` or `source`."
        " `mason schema <kind>` prints a Kind's fields.",
    ),
    "MSN103": Rule(
        "missing-version",
        checks="A config file has no `version`.",
        why="A Kind's schema can change between Mason releases. `version` says which schema a"
        " file is written against, so a newer Mason reads an older file as it was meant.",
        example=Example(
            {
                ORDERS: "kind: source\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Add `version` below `kind`, with the latest version this Mason supports, such as"
        " `version: 1`.",
    ),
    "MSN104": Rule(
        "unknown-version",
        checks="This Mason doesn't support that `version`.",
        why="The file is written against a schema this Mason doesn't have, usually because a"
        " newer Mason wrote it. Checking it against another version's schema would give wrong"
        " answers.",
        example=Example(
            {
                ORDERS: "kind: source\nversion: 2\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Use a version this Mason supports, which the diagnostic lists. If the file needs a"
        " newer Mason, upgrade Mason in the project so everyone runs the same one.",
    ),
    "MSN105": Rule(
        "wrong-kind",
        checks="A file's `kind` doesn't belong in its location.",
        why="Where a file lives says what it is: Sources in `sources/`, Seeds in `seeds/` and"
        " Gold Models in `models/`. When a file's `kind` disagrees with its folder, Mason can't"
        " tell which is right, so it doesn't guess.",
        example=Example(
            {
                ORDERS: "kind: model\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Change `kind` to the Kind its folder holds, or move the file to the folder for its"
        " Kind.",
    ),
    "MSN106": Rule(
        "invalid-field",
        checks="A field doesn't match its Kind's schema.",
        why="Each Kind's schema says which fields a file may have, their types, and which are"
        " required. Checking them with no workspace means a wrong field fails in review, not in"
        " a deploy. A field the schema doesn't have is a problem too, so a misspelt optional"
        " field isn't silently ignored.",
        example=Example(
            {
                ORDERS: "kind: source\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: 7\n"
            }
        ),
        fix="Correct the field the diagnostic names. `mason schema <kind>` prints every field"
        " of a Kind, its type and whether it's required.",
    ),
    "MSN107": Rule(
        "unreadable-config",
        checks="A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file"
        " isn't valid CSV.",
        why="Mason reads a file before it checks anything in it. A file it can't read can't be"
        " checked at all.",
        example=Example(
            {
                ORDERS: "kind: source\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: [json\n"
            }
        ),
        fix="Correct the YAML at the line the diagnostic gives, and make the file a mapping of"
        " fields that starts with `kind`. For a Seed's file, save it as UTF-8 and close every"
        " quoted value.",
    ),
    "MSN108": Rule(
        "sql-without-config",
        checks="A SQL file has no config file beside it.",
        why="A Gold Model is a SQL file and a config file beside it, which says it's a model and"
        " names the SQL. Mason reports a SQL file on its own rather than skipping it, so a model"
        " can't silently drop out of a deploy.",
        example=Example(
            {"domains/sales/models/fct_returns.sql": "SELECT order_id\nFROM sales.silver.orders\n"}
        ),
        fix="Add a config file with the same name beside it, with `kind: model`, `version: 1`"
        " and `sql` naming the SQL file.",
    ),
    "MSN109": Rule(
        "missing-sql-file",
        checks="A model names a SQL file that doesn't exist.",
        why="A Gold Model's config names the SQL that builds its table. Without that file there"
        " is nothing to build.",
        example=Example(
            {
                "domains/sales/models/fct_returns.yaml": "kind: model\nversion: 1\n"
                "sql: fct_returns.sql\n"
            }
        ),
        fix="Correct `sql`, or add the SQL file to the same folder.",
    ),
    "MSN110": Rule(
        "keys-without-sequence-by",
        checks="A Source's `silver` block has `keys` but no `sequence_by`.",
        why="With `keys`, silver keeps one row per key and applies each change to it. Changes can"
        " arrive out of order, so Mason needs a column that says which change is newest."
        " Without one, an older change could overwrite a newer one.",
        example=Example({ORDERS: LANDED_AS_JSON + "silver:\n  keys: [order_id]\n"}),
        fix="Add `sequence_by` with the column that orders the changes, such as `updated_at`,"
        " or remove `keys` to append every row.",
        principle=SILVER_IS_TYPED,
    ),
    "MSN111": Rule(
        "upsert-field-without-keys",
        checks="A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`.",
        why="These fields shape an upsert: which change is newest, whether history is kept, and"
        " which change is a delete. Each works on the rows of one key. Without `keys`, silver"
        " appends every row, so the field would do nothing while looking as if it did.",
        example=Example({ORDERS: LANDED_AS_JSON + "silver:\n  scd: 2\n"}),
        fix="Add `keys` with the columns that identify a row, or remove the field to append.",
        principle=SILVER_IS_TYPED,
    ),
    "MSN112": Rule(
        "missing-seed-file",
        checks="A Seed's `file` doesn't exist beside it.",
        why="A Seed is a small table kept in the repo as a CSV file and a config file. Without"
        " the CSV file there is no data to load.",
        example=Example({COUNTRIES: COUNTRIES_CONFIG}),
        fix="Correct `file`, or add the CSV file to the same folder.",
    ),
    "MSN113": Rule(
        "seed-header-mismatch",
        checks="The first line of a Seed's file doesn't name each declared column once.",
        why="Mason matches a Seed's values to its columns by the names on the first line, then"
        " checks each value against its column's type. A first line that doesn't name each"
        " column once leaves values with no column, or a column with no values.",
        example=Example({COUNTRIES: COUNTRIES_CONFIG, COUNTRIES_CSV: "country\nAU\n"}),
        fix="Make the first line name each declared column once, or change `columns` in the"
        " Seed's config file.",
    ),
    "MSN114": Rule(
        "seed-row-mismatch",
        checks="A row of a Seed's file has the wrong number of values, or a value that doesn't"
        " fit its column's type.",
        why="Mason checks a Seed's values before deploying it, so a typo in the CSV file fails"
        " in review rather than when the table loads.",
        example=Example(
            {
                COUNTRIES: COUNTRIES_CONFIG + "  population: INT\n",
                COUNTRIES_CSV: "code,population\nAU,26 million\n",
            }
        ),
        fix="Give each row one value per column, quoting any value that contains a comma, and"
        " make each value fit its column's type, or change the type.",
    ),
    "MSN115": Rule(
        "unsupported-seed-type",
        checks="A Seed's column has a type Mason can't check values against.",
        why="Mason checks every value in a Seed against its column's type. A type it can't"
        " check, often a misspelt one, would let any value through.",
        example=Example(
            {
                COUNTRIES: "kind: seed\nversion: 1\nfile: countries.csv\n"
                "columns:\n  code: VARCAHR\n",
                COUNTRIES_CSV: "code\nAU\n",
            }
        ),
        fix="Use a type Mason checks, which the diagnostic lists, such as `STRING`, `INT`,"
        " `DATE` or `DECIMAL(10, 2)`.",
    ),
    "MSN116": Rule(
        "invalid-expectation",
        checks="An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse,"
        " or it holds a query, an aggregate, a window function, a comment or an alias.",
        why="An Expectation is checked on each row as it's written to silver, so its condition"
        " can see only that row. A query, an aggregate or a window function reads other rows,"
        " and a rule across rows is a Test. Mason places `expect` inside the code it generates,"
        " so it must parse on its own, and a comment would hide the code after it.",
        example=Example(
            {
                ORDERS: LANDED_AS_JSON
                + "silver:\n  expectations:\n    - name: amount_is_positive\n"
                "      expect: amount > (SELECT avg(amount) FROM sales.silver.orders)\n"
            }
        ),
        fix="Write `expect` as one condition on the row's own columns, such as `amount > 0`. A"
        " rule across rows is a Test.",
        principle=EXPECTATIONS_GUARD_ROWS,
    ),
    "MSN117": Rule(
        "invalid-name",
        checks="A config file's name isn't an identifier, so the table named after it can't be"
        " written in SQL: it must hold only letters, digits and underscores, and not start with"
        " a digit.",
        why="A Source, Seed or Gold Model takes its table's name from its config file's name, and"
        " SQL reads that table by name. A name with a hyphen or a space, or one that starts with"
        " a digit, would need quoting everywhere it's read.",
        example=Example(
            {
                "domains/sales/seeds/vat-rates.yaml": "kind: seed\nversion: 1\n"
                "file: vat-rates.csv\ncolumns:\n  code: STRING\n",
                "domains/sales/seeds/vat-rates.csv": "code\nAU\n",
            }
        ),
        fix="Rename the file to a name of letters, digits and underscores, such as"
        " `vat_rates.yaml`, which the diagnostic suggests.",
    ),
    "MSN118": Rule(
        "invalid-delete-when",
        checks="A Source's `silver.delete_when` isn't one SQL condition on one row, for the same"
        " reasons as `MSN116`.",
        why="`delete_when` decides, change by change, whether a change deletes its key's row,"
        " so it can see only that change. Mason places it inside the code it generates, so it"
        " must parse on its own, and a comment would hide the code after it.",
        example=Example(
            {
                ORDERS: LANDED_AS_JSON + "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n"
                "  delete_when: op = 'D' -- deletes from the source system\n"
            }
        ),
        fix="Write `delete_when` as one condition on the row's own columns, such as `op = 'D'`.",
        principle=SILVER_IS_TYPED,
    ),
    "MSN119": Rule(
        "invalid-sequence-by",
        checks="A Source's `silver.sequence_by` isn't one SQL expression on one row, such as"
        " `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an"
        " aggregate, a window function, a comment or an alias.",
        why="`sequence_by` orders the changes to each key, so silver keeps the newest. Mason"
        " places it inside the code it generates, so it must be one expression on the change's"
        " own columns. A sort direction such as `DESC` reads as an alias, and has no place"
        " there: the highest value is always the newest.",
        example=Example(
            {
                ORDERS: LANDED_AS_JSON
                + "silver:\n  keys: [order_id]\n  sequence_by: updated_at DESC\n"
            }
        ),
        fix="Write `sequence_by` as the column that orders the changes, such as `updated_at`, or"
        " one expression on the row's own columns, such as `struct(updated_at, seq)`.",
        principle=SILVER_IS_TYPED,
    ),
    "MSN120": Rule(
        "duplicate-config-file",
        checks="Two config files share a name in one folder, such as `orders.yaml` and"
        " `orders.yml`. Mason reads either ending, and writes `.yaml`.",
        why="A config file's name is its table's name, so two files with one name would declare"
        " one table twice, and Mason can't tell which one is meant.",
        example=Example({"domains/sales/sources/orders.yml": LANDED_AS_JSON}),
        fix="Keep one of the files, and delete or rename the other.",
    ),
    "MSN121": Rule(
        "unlisted-domain-folder",
        checks="A folder under `domains/` isn't listed in `domains` in `mason.platform.yaml`, in"
        " the same case, so nothing in it is validated or deployed.",
        why="`domains` in `mason.platform.yaml` lists the project's Domains, and Mason reads only"
        " those folders. A folder it doesn't list would be silently left out of every check and"
        " every deploy. A folder that differs only in case is found on some file systems and"
        " not others, so it's reported too.",
        example=Example(
            {
                "domains/hr/sources/employees.yaml": "kind: source\nversion: 1\n"
                "path: /Volumes/{env}_hr/bronze/landing/employees\nformat: json\n"
            }
        ),
        fix="Add the folder to `domains` in `mason.platform.yaml`, matching its case, or remove"
        " the folder.",
    ),
    "MSN201": Rule(
        "unresolved-logical-name",
        checks="SQL reads a table that isn't in the project.",
        why="Mason knows every table a project makes: each Source's bronze and silver tables,"
        " each Seed's table and each Gold Model's table. SQL reads them by Logical Name, such as"
        " `sales.silver.orders`, so Mason can check every read before a deploy and point it at"
        " the right catalog in each Environment. A read it can't find is a typo, or a table"
        " nothing in the project makes. A table name without its Domain and Layer that isn't a"
        " CTE is reported too, because Mason can't tell which table it means.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.silver.order\n"}),
        fix="Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
        principle=EVERY_CATALOG_IS_ONE_DOMAIN,
    ),
    "MSN202": Rule(
        "duplicate-table",
        checks="A Seed and a Source in one Domain share a name, so they would be one table.",
        why="A Seed's table is in silver, beside each Source's silver table. A Seed and a Source"
        " with one name in one Domain would write the same table, and one would overwrite the"
        " other.",
        example=Example(
            {
                "domains/sales/seeds/orders.yaml": "kind: seed\nversion: 1\nfile: orders.csv\n"
                "columns:\n  order_id: INT\n",
                "domains/sales/seeds/orders.csv": "order_id\n1\n",
            }
        ),
        fix="Rename the Seed or the Source, so each has its own table.",
    ),
    "MSN203": Rule(
        "unparseable-sql",
        checks="A Gold Model's SQL doesn't parse as one Databricks SQL query.",
        why="Mason reads a Gold Model's SQL to find every table it reads, so it can check them,"
        " build them first and point each at the right Environment. SQL it can't parse hides"
        " those reads. A file with more than one statement is reported too, because a Gold"
        " Model is one query.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.silver.orders\nWHERE\n"}),
        fix="Make the file one Databricks SQL query that runs on its own.",
    ),
    "MSN204": Rule(
        "computed-table-name",
        checks="SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Mason can't"
        " see what it reads.",
        why="Mason checks every table a Gold Model reads, and shows those reads in review. A name"
        " built when the query runs can't be seen until then, so it could read any table in any"
        " Environment.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM IDENTIFIER(:orders_table)\n"}),
        fix="Write the table as a Logical Name, such as `sales.silver.orders`.",
        principle=EVERY_CHANGE_IS_REVIEWED,
    ),
    "MSN205": Rule(
        "real-table-name",
        checks="SQL reads a real table name, which names one Environment, instead of its Logical"
        " Name.",
        why="A real table name such as `dev_sales.silver.orders` names one Environment's"
        " catalog, so the same SQL would read dev data in prod. A Logical Name such as"
        " `sales.silver.orders` names no Environment, and Mason points it at the right catalog"
        " in each.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM dev_sales.silver.orders\n"}),
        fix="Use the table's Logical Name, which the diagnostic gives. If no table in the project"
        " has that name, declare a Source, Seed or Gold Model for it.",
        principle=EVERY_CATALOG_IS_ONE_DOMAIN,
    ),
    "MSN206": Rule(
        "file-read",
        checks="A Gold Model reads files or external data, such as `read_files(...)` or"
        " ``parquet.`/path` ``, instead of a table.",
        why="A Gold Model reads tables in the project. Data read straight from files skips"
        " bronze and silver, so it isn't landed, typed or checked, and Mason can't point the"
        " path at each Environment.",
        example=Example(
            {
                FCT_ORDERS: "SELECT order_id, amount\n"
                "FROM read_files('/Volumes/prod_sales/bronze/landing/orders')\n"
            }
        ),
        fix="Declare a Source for these files, and read its silver table by Logical Name.",
        principle=DATA_FLOWS_ONE_WAY,
    ),
    "MSN207": Rule(
        "raw-string-placeholder",
        checks="A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`.",
        why="The pipeline replaces `${name}` with a setting's value anywhere in its SQL, even"
        " inside a string. Mason escapes `${` in ordinary strings and comments, so they keep"
        " the value you wrote, but a raw string can't hold the escape.",
        example=Example(
            {FCT_ORDERS: "SELECT order_id, r'${order_id}' AS template\nFROM sales.silver.orders\n"}
        ),
        fix="Write it as an ordinary string, doubling each backslash, and Mason escapes the `${`.",
    ),
    "MSN208": Rule(
        "model-cycle",
        checks="Gold Models read themselves, or each other in a loop, so none of them can run"
        " first.",
        why="Mason builds each Gold Model after the tables it reads. When Gold Models read each"
        " other in a loop, every one of them waits for another, so there is no order to build"
        " them in.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.gold.fct_orders\n"}),
        fix="Remove one of the reads in the loop, which the diagnostic lists, so each Gold Model"
        " reads only tables built before it.",
    ),
    "MSN901": Rule(
        "usage-error",
        checks="The command line is wrong.",
        why="A command, option or argument is unknown or missing. With `--json`, Mason still"
        " prints one envelope, so a script or agent reads the problem instead of help text. It"
        " exits 2, because the command line needs a change, not the project.",
        example=Example(command="mason validate --projct ."),
        fix="Correct the command line. `mason <command> --help` lists a command's options.",
    ),
    "MSN902": Rule(
        "unknown-environment",
        checks="`--env` isn't an Environment in the project.",
        why="Environments are declared in `mason.platform.yaml`, each with its workspace. An"
        " Environment that isn't there has no workspace or catalogs to compile or deploy for.",
        example=Example(command="mason compile --env staging"),
        fix="Use an Environment from `mason.platform.yaml`, which the diagnostic lists, or add"
        " the Environment there.",
    ),
    "MSN903": Rule(
        "databricks-cli-missing",
        checks="`databricks` isn't on the PATH.",
        why="Mason deploys through the Databricks CLI. It isn't installed, or isn't on the PATH"
        " of the shell that ran Mason, such as a CI job.",
        example=Example(
            command="mason deploy --env dev", when="The Databricks CLI isn't installed."
        ),
        fix="Install the Databricks CLI and put `databricks` on your PATH."
        " `databricks --version` checks it.",
    ),
    "MSN904": Rule(
        "databricks-command-failed",
        checks="A Databricks CLI command failed.",
        why="Mason ran a Databricks CLI command, such as `databricks bundle deploy`, and it"
        " failed. Its log on stderr says why, often authentication, permissions or the"
        " workspace itself. A refresh that fails reports this Rule too when Mason can't read the"
        " pipeline's own error.",
        example=Example(
            command="mason deploy --env dev",
            when="The Databricks CLI isn't signed in to the dev workspace.",
        ),
        fix="Read the Databricks CLI's log on stderr, fix what it names, and run the command"
        " again. `databricks auth describe` checks how the CLI signs in.",
    ),
    "MSN905": Rule(
        "unexpected-error",
        checks="Mason stopped on something it didn't expect, with a traceback on stderr.",
        why="Something went wrong that isn't a problem in the project or on the command line."
        " Mason still reports it as a diagnostic, as an envelope with `--json`, and exits 2, so"
        " scripts keep working.",
        example=Example(command="mason compile", when="The disk is full."),
        fix="Read the traceback on stderr. If your machine isn't the cause, report a bug at"
        " https://github.com/nimblestax/mason-core/issues with the traceback.",
    ),
    "MSN906": Rule(
        "pipeline-column-not-found",
        checks="The refresh failed because a pipeline names a column its table doesn't have,"
        " often an Expectation on a column bronze doesn't have yet.",
        why="`mason deploy` refreshes an Environment's tables after it ships them, and reports a"
        " pipeline's own error when an update fails. When an Expectation checks a column that"
        " arrives in the same change, the silver flow fails on the unknown column before bronze"
        " runs, so bronze never picks the column up, and landing new data doesn't help.",
        example=Example(
            command="mason deploy --env dev",
            when="A Source's files gained a `region` column, and an Expectation on `region` was"
            " added in the same change.",
        ),
        fix="Correct the column's name. If an Expectation names a column bronze doesn't have"
        " yet, deploy without the Expectation so bronze picks up the column, then add it back."
        f" See {RECOVERY_GUIDE}.",
    ),
    "MSN907": Rule(
        "expectation-failed",
        checks="The refresh failed because a row broke an Expectation whose `action` is `fail`.",
        why="An Expectation with `action: fail` stops the update when a row breaks it. Bronze is"
        " append-only, so the row stays there, and every refresh fails on it until the rule"
        " changes. Landing a corrected row doesn't remove the bad one.",
        example=Example(
            command="mason deploy --env dev",
            when="A row in bronze has a negative `amount`, and the Source has an Expectation"
            " `amount >= 0` with `action: fail`.",
        ),
        fix="Correct the rule if the row is fine, or change its `action` to `quarantine` or"
        f" `warn`, then deploy again. See {RECOVERY_GUIDE}.",
        principle=EXPECTATIONS_GUARD_ROWS,
    ),
    "MSN908": Rule(
        "pipeline-failed",
        checks="The refresh failed with another pipeline error. The message is the pipeline's"
        " own.",
        why="`mason deploy` refreshes an Environment's tables after it ships them. When a"
        " pipeline update fails for a reason Mason has no Rule for, it reports the pipeline's"
        " own error, read from its event log, rather than a generic failure.",
        example=Example(
            command="mason deploy --env dev",
            when="The pipeline can't read the Volume a Source's files land in.",
        ),
        fix="Fix the cause, then deploy again. The pipeline's event log in the workspace has"
        " more.",
    ),
}
