import csv
import datetime

FileName = "tenants.csv"
FieldNames = ["TenantID", "Name", "Unit", "RentAmount", "LeaseStart", "LeaseEnd", "TotalPaid"]

# Index positions inside each tenant's list, so the numbers below have names
NameIndex = 0
UnitIndex = 1
RentAmountIndex = 2
LeaseStartIndex = 3
LeaseEndIndex = 4
TotalPaidIndex = 5


def InitializeFile():
    # Creates the CSV file with headers if it does not already exist
    try:
        FileObject = open(FileName, "r")
        FileObject.close()
    except FileNotFoundError:
        FileObject = open(FileName, "w", newline="")
        Writer = csv.writer(FileObject)
        Writer.writerow(FieldNames)
        FileObject.close()
        print("New tenant file created:", FileName)


def LoadData():
    # Reads the CSV file once and builds a dictionary in memory
    # Each key is a TenantID, each value is a list in this fixed order:
    # [Name, Unit, RentAmount, LeaseStart, LeaseEnd, TotalPaid]
    TenantData = {}
    FileObject = open(FileName, "r", newline="")
    Reader = csv.DictReader(FileObject)

    for Row in Reader:
        TenantID = Row["TenantID"]

        LeaseStartDate = datetime.datetime.strptime(Row["LeaseStart"], "%Y-%m-%d").date()

        if Row["LeaseEnd"] == "":
            LeaseEndDate = None
        else:
            LeaseEndDate = datetime.datetime.strptime(Row["LeaseEnd"], "%Y-%m-%d").date()

        TenantData[TenantID] = [
            Row["Name"],
            Row["Unit"],
            float(Row["RentAmount"]),
            LeaseStartDate,
            LeaseEndDate,
            float(Row["TotalPaid"])
        ]

    FileObject.close()
    return TenantData


def SaveData(TenantData):
    # Writes the entire dictionary back to the CSV file
    FileObject = open(FileName, "w", newline="")
    Writer = csv.writer(FileObject)
    Writer.writerow(FieldNames)

    for TenantID in TenantData:
        Record = TenantData[TenantID]

        if Record[LeaseEndIndex] is None:
            LeaseEndText = ""
        else:
            LeaseEndText = Record[LeaseEndIndex].strftime("%Y-%m-%d")

        Row = [
            TenantID,
            Record[NameIndex],
            Record[UnitIndex],
            Record[RentAmountIndex],
            Record[LeaseStartIndex].strftime("%Y-%m-%d"),
            LeaseEndText,
            Record[TotalPaidIndex]
        ]
        Writer.writerow(Row)

    FileObject.close()


def BackupFile():
    # Makes a timestamped copy of the current file before changes are saved
    try:
        OriginalFile = open(FileName, "r", newline="")
    except FileNotFoundError:
        return

    FileContent = OriginalFile.read()
    OriginalFile.close()

    TimeStamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    BackupName = "tenants_backup_" + TimeStamp + ".csv"

    BackupFileObject = open(BackupName, "w", newline="")
    BackupFileObject.write(FileContent)
    BackupFileObject.close()

    print("Backup created:", BackupName)


def AddTenant(TenantData):
    TenantID = input("Enter Tenant ID: ")

    if TenantID in TenantData:
        print("A tenant with this ID already exists.")
        return

    Name = input("Enter Name: ")
    Unit = input("Enter Unit Number: ")
    RentAmount = float(input("Enter Monthly Rent Amount: "))
    LeaseStartText = input("Enter Lease Start Date (YYYY-MM-DD): ")
    LeaseStartDate = datetime.datetime.strptime(LeaseStartText, "%Y-%m-%d").date()

    TenantData[TenantID] = [Name, Unit, RentAmount, LeaseStartDate, None, 0.0]

    BackupFile()
    SaveData(TenantData)
    print("Tenant added successfully.")


def EndLease(TenantData):
    TenantID = input("Enter Tenant ID: ")

    if TenantID not in TenantData:
        print("Tenant not found.")
        return

    EndDateText = input("Enter Lease End Date (YYYY-MM-DD): ")
    EndDate = datetime.datetime.strptime(EndDateText, "%Y-%m-%d").date()

    TenantData[TenantID][LeaseEndIndex] = EndDate

    BackupFile()
    SaveData(TenantData)
    print("Lease ended for tenant", TenantID)


def LogPayment(TenantData):
    TenantID = input("Enter Tenant ID: ")

    if TenantID not in TenantData:
        print("Tenant not found.")
        return

    AmountPaid = float(input("Enter Payment Amount: "))
    TenantData[TenantID][TotalPaidIndex] = TenantData[TenantID][TotalPaidIndex] + AmountPaid

    BackupFile()
    SaveData(TenantData)
    print("Payment recorded for tenant", TenantID)


def CalculateBalance(TenantRecord):
    # Works out days passed, months passed, expected rent, and balance due
    Today = datetime.date.today()

    if TenantRecord[LeaseEndIndex] is None:
        EndPoint = Today
    else:
        EndPoint = min(Today, TenantRecord[LeaseEndIndex])

    DaysPassed = (EndPoint - TenantRecord[LeaseStartIndex]).days
    TotalMonths = DaysPassed // 30
    ExpectedAmount = TotalMonths * TenantRecord[RentAmountIndex]
    Balance = ExpectedAmount - TenantRecord[TotalPaidIndex]

    return DaysPassed, TotalMonths, ExpectedAmount, Balance


def ShowTenantDetails(TenantData):
    TenantID = input("Enter Tenant ID: ")

    if TenantID not in TenantData:
        print("Tenant not found.")
        return

    Record = TenantData[TenantID]
    DaysPassed, TotalMonths, ExpectedAmount, Balance = CalculateBalance(Record)

    print("\n--- Tenant Details ---")
    print("Tenant ID:", TenantID)
    print("Name:", Record[NameIndex])
    print("Unit:", Record[UnitIndex])
    print("Rent Amount:", Record[RentAmountIndex])
    print("Lease Start:", Record[LeaseStartIndex])
    print("Lease End:", Record[LeaseEndIndex])
    print("Days Passed:", DaysPassed)
    print("Total Months:", TotalMonths)
    print("Expected Amount:", ExpectedAmount)
    print("Total Paid:", Record[TotalPaidIndex])

    if Balance > 0:
        print("Balance Due:", Balance)
    else:
        print("No Balance Due. Fully Paid or Overpaid by:", -Balance)


def ShowAllTenants(TenantData):
    print("\n--- All Tenants ---")

    for TenantID in TenantData:
        Record = TenantData[TenantID]
        print(TenantID, "-", Record[NameIndex], "-", "Unit:", Record[UnitIndex])


def ShowOverdueTenants(TenantData):
    print("\n--- Overdue Tenants ---")
    FoundAny = False

    for TenantID in TenantData:
        Record = TenantData[TenantID]
        DaysPassed, TotalMonths, ExpectedAmount, Balance = CalculateBalance(Record)

        if Balance > 0:
            FoundAny = True
            print(TenantID, "-", Record[NameIndex], "- Balance Due:", Balance)

    if FoundAny == False:
        print("No tenants are currently overdue.")


# ---------------- Main Program ----------------

InitializeFile()
TenantData = LoadData()

while True:
    print("\n===== Multi-Tenant Management System =====")
    print("1. Add Tenant")
    print("2. End Lease")
    print("3. Log Payment")
    print("4. View Tenant Details")
    print("5. View All Tenants")
    print("6. View Overdue Tenants")
    print("7. Exit")

    Choice = input("Enter your choice: ")

    if Choice == "1":
        AddTenant(TenantData)
    elif Choice == "2":
        EndLease(TenantData)
    elif Choice == "3":
        LogPayment(TenantData)
    elif Choice == "4":
        ShowTenantDetails(TenantData)
    elif Choice == "5":
        ShowAllTenants(TenantData)
    elif Choice == "6":
        ShowOverdueTenants(TenantData)
    elif Choice == "7":
        print("Exiting program. Goodbye!")
        break
    else:
        print("Invalid choice. Please try again.")
