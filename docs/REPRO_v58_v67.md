# Reproducing the v58 / v67 measurement

**~15 minutes in a fresh scratch org. Nothing here is specific to any tooling — it is
the platform's own behaviour, and you should be able to disprove it if it is wrong.**

This is the setup behind the claim that byte-identical Apex returns 5 records at API
v58 and 0 at v67. Measured on Salesforce Summer '26.

---

## 1. The object

```
Sharing_Test__c
  sharingModel: Private        ← so the record axis can actually hide something
```

## 2. Two text fields — and the second one is the point

```
Customer_IBAN__c    Text     ← the field under test
Secret_Data__c      Text     ← the NEGATIVE CONTROL (see step 6)
```

## 3. The data

Create **5 records owned by the admin**, with a real value in **both** fields.

Admin-owned matters: under `Private` OWD the test user must not own them, or sharing
has nothing to hide and the record axis is untested.

## 4. The user

A user — or a permission set on a throwaway user — with **exactly** this:

```
Object   Sharing_Test__c    Read = true
                          Create / Edit / Delete = false
                          View All / Modify All  = false

System   ViewAllData = false
         ModifyAllData = false

Field    Secret_Data__c      Read = true        ← the control
         Customer_IBAN__c    (no entry at all)  ← deliberately NO field permission
```

## 5. The Apex — one class, two lines

```apex
public without sharing class B {
    public static Integer m() {
        List<Sharing_Test__c> r = [SELECT Customer_IBAN__c FROM Sharing_Test__c];
        return r.size();
    }
}
```

And its metadata file — **this is the whole experiment**:

```xml
<!-- B.cls-meta.xml -->
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>58.0</apiVersion>
    <status>Active</status>
</ApexClass>
```

## 6. Run it twice, as that user

Execute `B.m()` **as the test user** — anonymous Apex runs as you, so use
`System.runAs` in a test, or authenticate as the user.

Then change **only the number** in `B.cls-meta.xml` to `67.0`, redeploy the same
`.cls`, and run again.

```
apiVersion 58.0   →   5     rows returned, IBAN value readable
apiVersion 67.0   →   0     and the field reference itself is rejected:
                            System.QueryException: No such column 'Customer_IBAN__c'
```

### Why the control field exists

Run the same query against `Secret_Data__c` — the field the user **is** entitled to.
It returns data at both versions.

That is what makes the v67 zero mean something. Without the control, a zero could be
"the query was broken" or "there were no rows to begin with". With it, the zero is
the platform bounding the read.

**An escape means the data came back AND the user was not entitled to it — both
facts, never one.**

## What it demonstrates

Two independent axes, and the API version moves both:

| | v58 (`without sharing`) | v67 (same source) |
|---|---|---|
| **Record visibility** (sharing) | bypassed → sees the admin's rows | enforced → 0 rows |
| **Field security** (CRUD + FLS) | bypassed → IBAN readable | enforced → **throws** |

From API v67, Salesforce defaults to user mode. Below it, the same source defaults to
system mode. And the platform **blocks** rather than silently stripping — which is the
behaviour you want, and not what most people assume when they hear "FLS is enforced".

## The variation worth running next

Keep everything the same and change only the sharing declaration:

| declaration at v58 | rows returned |
|---|---|
| `without sharing` | 5 |
| *(no declaration)* | 0 |
| `with sharing` | 0 |

"No declaration" is **not** the same as `without sharing` — a class with no
declaration inherits its caller's context. This one surprises people more than the
version difference does.

---

*Measured on Summer '26. Platform behaviour changes between releases; if this stops
reproducing, that is a finding worth reporting.*
