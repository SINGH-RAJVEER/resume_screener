import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Plus, X } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";
import type { PointsSummary } from "../../lib/billing-types";
import { openCheckout } from "../../lib/razorpay";
import {
	billingClient,
	type JoinPolicy,
	type Member,
	type Organization,
	type PointPack,
	workspaceClient,
} from "./client";
import { overlayBackdrop } from "./shared";

const ENTERPRISE_SALES_EMAIL =
	import.meta.env.VITE_ENTERPRISE_SALES_EMAIL ?? "sales@skillsignal.app";

type MembersDialogProps = {
	organization: Organization;
	onDismiss: () => void;
	onNotice: (message: string) => void;
	onError: (reason: unknown) => void;
};

export const MembersDialog = ({
	organization,
	onDismiss,
	onNotice,
	onError,
}: MembersDialogProps) => {
	const organizationId = organization.id;
	const isOwner = organization.role === "owner";
	const [members, setMembers] = useState<Member[]>([]);
	const [memberEmail, setMemberEmail] = useState("");
	const [memberRole, setMemberRole] =
		useState<Pick<Member, "role">["role"]>("recruiter");
	const [joinPolicy, setJoinPolicy] = useState<JoinPolicy | null>(null);
	const [policyDomain, setPolicyDomain] = useState("");
	const [policyEmail, setPolicyEmail] = useState("");
	const [orgPoints, setOrgPoints] = useState<PointsSummary | null>(null);
	const [orgPacks, setOrgPacks] = useState<PointPack[]>([]);
	const [isAddingMember, setIsAddingMember] = useState(false);
	const [removingUserId, setRemovingUserId] = useState<string | null>(null);

	useEffect(() => {
		const load = async () => {
			try {
				setMembers(await workspaceClient.members(organizationId));
				if (isOwner) {
					setJoinPolicy(
						await workspaceClient.joinPolicy(organizationId),
					);
				}
			} catch (reason) {
				onError(reason);
			}
		};
		void load();
		billingClient
			.orgPoints(organizationId)
			.then(setOrgPoints)
			.catch(() => setOrgPoints(null));
		billingClient
			.packs()
			.then(setOrgPacks)
			.catch(() => setOrgPacks([]));
	}, [organizationId, isOwner, onError]);

	const addMember = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!memberEmail.trim() || isAddingMember) return;
		setIsAddingMember(true);
		try {
			const added = await workspaceClient.addMember(
				organizationId,
				memberEmail,
				memberRole,
			);
			setMemberEmail("");
			setMemberRole("recruiter");
			setMembers(await workspaceClient.members(organizationId));
			onNotice(`Member added as ${added.role}.`);
		} catch (reason) {
			onError(reason);
		} finally {
			setIsAddingMember(false);
		}
	};

	const removeMember = async (userId: string) => {
		if (removingUserId !== null) return;
		setRemovingUserId(userId);
		try {
			await workspaceClient.removeMember(organizationId, userId);
			setMembers(await workspaceClient.members(organizationId));
			onNotice("Member removed.");
		} catch (reason) {
			onError(reason);
		} finally {
			setRemovingUserId(null);
		}
	};

	const refreshJoinPolicy = async () => {
		setJoinPolicy(await workspaceClient.joinPolicy(organizationId));
	};

	const [buyingPack, setBuyingPack] = useState(false);

	const buyOrgPoints = async (packId: string) => {
		if (buyingPack) return;
		setBuyingPack(true);
		try {
			const order = await billingClient.createOrder(
				packId,
				organizationId,
			);
			await openCheckout({
				key: order.razorpayKeyId,
				orderId: order.razorpayOrderId,
				amountPaise: order.amountInr * 100,
				currency: order.currency,
				name: "SkillSignal organization points",
				description: `${order.points} points`,
				handler: async (response) => {
					try {
						await billingClient.verifyCheckout(
							order.id,
							response.razorpay_payment_id,
							response.razorpay_signature,
						);
						setOrgPoints(
							await billingClient.orgPoints(organizationId),
						);
					} catch (reason) {
						onError(reason);
					}
				},
			});
		} catch (reason) {
			onError(reason);
		} finally {
			setBuyingPack(false);
		}
	};

	const changeDefaultRole = async (
		defaultRole: JoinPolicy["defaultRole"],
	) => {
		try {
			await workspaceClient.setJoinPolicyDefaultRole(
				organizationId,
				defaultRole,
			);
			await refreshJoinPolicy();
			onNotice("Join policy updated.");
		} catch (reason) {
			onError(reason);
		}
	};

	const addPolicyDomain = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!policyDomain.trim()) return;
		try {
			const added = await workspaceClient.addJoinPolicyDomain(
				organizationId,
				policyDomain,
			);
			setPolicyDomain("");
			await refreshJoinPolicy();
			onNotice(`@${added.domain} can now join.`);
		} catch (reason) {
			onError(reason);
		}
	};

	const removePolicyDomain = async (domain: string) => {
		try {
			await workspaceClient.removeJoinPolicyDomain(
				organizationId,
				domain,
			);
			await refreshJoinPolicy();
			onNotice("Domain rule removed. Existing members keep access.");
		} catch (reason) {
			onError(reason);
		}
	};

	const addPolicyEmail = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!policyEmail.trim()) return;
		try {
			const added = await workspaceClient.addJoinPolicyEmail(
				organizationId,
				policyEmail,
			);
			setPolicyEmail("");
			await refreshJoinPolicy();
			onNotice(`${added.email} can now join.`);
		} catch (reason) {
			onError(reason);
		}
	};

	const removePolicyEmail = async (email: string) => {
		try {
			await workspaceClient.removeJoinPolicyEmail(organizationId, email);
			await refreshJoinPolicy();
			onNotice("Email rule removed. Existing members keep access.");
		} catch (reason) {
			onError(reason);
		}
	};

	return (
		<div
			{...overlayBackdrop({
				labelledBy: "members-title",
				onDismiss,
			})}
		>
			<div className="modal-panel">
				<div className="modal-head-row">
					<h3 id="members-title">Members · {organization.name}</h3>
					<button
						aria-label="Close members"
						className="icon-button"
						onClick={onDismiss}
						type="button"
					>
						<X />
					</button>
				</div>
				<div className="member-list">
					{members.map((member) => (
						<div className="member-row" key={member.userId}>
							<span>
								<span style={{ fontWeight: 600 }}>
									{member.name}
								</span>
								<span className="candidate-email">
									{member.email}
								</span>
							</span>
							<span className="member-side">
								<span className="status-chip chip-muted">
									{member.role}
								</span>
								{isOwner && member.role !== "owner" && (
									<Button
										disabled={removingUserId !== null}
										onClick={() =>
											void removeMember(member.userId)
										}
										size="sm"
										variant="outline"
									>
										{removingUserId === member.userId
											? "Removing..."
											: "Remove"}
									</Button>
								)}
							</span>
						</div>
					))}
					{members.length === 0 && (
						<p className="muted-copy loading-inline">
							<ThinkingOrb
								aria-hidden
								size={20}
								state="solving"
							/>
							Loading members...
						</p>
					)}
				</div>
				{isOwner ? (
					<form className="member-form" onSubmit={addMember}>
						<Input
							aria-label="Member email"
							onChange={(event) =>
								setMemberEmail(event.target.value)
							}
							placeholder="colleague@company.com"
							required
							type="email"
							value={memberEmail}
						/>
						<select
							aria-label="Member role"
							className="workspace-filter-select"
							onChange={(event) =>
								setMemberRole(
									event.target.value as Member["role"],
								)
							}
							value={memberRole}
						>
							<option value="recruiter">Recruiter</option>
							<option value="viewer">Viewer</option>
						</select>
						<Button
							disabled={isAddingMember}
							size="sm"
							type="submit"
						>
							<Plus />
							{isAddingMember ? "Adding..." : "Add member"}
						</Button>
					</form>
				) : (
					<p className="muted-copy">
						Only owners can add or remove members.
					</p>
				)}
				{isOwner && joinPolicy && (
					<div className="join-policy">
						<h4 className="join-policy-title">Access</h4>
						<p className="muted-copy">
							New employer accounts matching a rule below join
							this organization automatically with the default
							role. Removing a rule never removes existing
							members.
						</p>
						<div className="member-row">
							<span style={{ fontWeight: 600 }}>
								Default role for new members
							</span>
							<select
								aria-label="Default member role"
								className="workspace-filter-select"
								onChange={(event) =>
									void changeDefaultRole(
										event.target
											.value as JoinPolicy["defaultRole"],
									)
								}
								value={joinPolicy.defaultRole}
							>
								<option value="recruiter">Recruiter</option>
								<option value="viewer">Viewer</option>
							</select>
						</div>
						{joinPolicy.domains.length > 0 && (
							<div className="member-list">
								{joinPolicy.domains.map((domain) => (
									<div className="member-row" key={domain}>
										<span className="candidate-email">
											@{domain}
										</span>
										<span className="member-side">
											<Button
												onClick={() =>
													void removePolicyDomain(
														domain,
													)
												}
												size="sm"
												variant="outline"
											>
												Remove
											</Button>
										</span>
									</div>
								))}
							</div>
						)}
						<form
							className="member-form"
							onSubmit={addPolicyDomain}
						>
							<Input
								aria-label="Allowed email domain"
								onChange={(event) =>
									setPolicyDomain(event.target.value)
								}
								placeholder="@company.com"
								value={policyDomain}
							/>
							<Button size="sm" type="submit">
								<Plus />
								Allow domain
							</Button>
						</form>
						{joinPolicy.emails.length > 0 && (
							<div className="member-list">
								{joinPolicy.emails.map((email) => (
									<div className="member-row" key={email}>
										<span className="candidate-email">
											{email}
										</span>
										<span className="member-side">
											<Button
												onClick={() =>
													void removePolicyEmail(
														email,
													)
												}
												size="sm"
												variant="outline"
											>
												Remove
											</Button>
										</span>
									</div>
								))}
							</div>
						)}
						<form className="member-form" onSubmit={addPolicyEmail}>
							<Input
								aria-label="Allowed email address"
								onChange={(event) =>
									setPolicyEmail(event.target.value)
								}
								placeholder="contractor@personal.org"
								type="email"
								value={policyEmail}
							/>
							<Button size="sm" type="submit">
								<Plus />
								Allow email
							</Button>
						</form>
					</div>
				)}
				{orgPoints && (
					<div className="join-policy">
						<h4 className="join-policy-title">Points</h4>
						<p className="muted-copy">
							Evaluating one resume reserves up to the quoted
							maximum from this balance.{" "}
							{orgPoints.enterprise
								? "An enterprise entitlement covers batch evaluations without points."
								: "Contact sales for organization-wide enterprise access."}
						</p>
						<div className="member-row">
							<span style={{ fontWeight: 600 }}>
								{`${orgPoints.balance} points available`}
							</span>
						</div>
						{isOwner && orgPacks.length > 0 && (
							<form className="member-form">
								<select
									aria-label="Point pack"
									className="workspace-filter-select"
									id="org-point-pack"
									defaultValue={orgPacks[0]?.id ?? ""}
								>
									{orgPacks.map((pack) => (
										<option
											key={pack.id}
											value={pack.id}
										>{`${pack.points.toLocaleString()} points · ₹${pack.amountInr}`}</option>
									))}
								</select>
								<Button
									disabled={buyingPack}
									onClick={() => {
										const select = document.getElementById(
											"org-point-pack",
										) as HTMLSelectElement | null;
										if (select)
											void buyOrgPoints(select.value);
									}}
									size="sm"
									type="button"
								>
									{buyingPack
										? "Opening checkout"
										: "Buy points"}
								</Button>
							</form>
						)}
						{!orgPoints.enterprise && (
							<a
								className="candidate-email"
								href={`mailto:${ENTERPRISE_SALES_EMAIL}`}
							>
								Contact sales about enterprise access
							</a>
						)}
					</div>
				)}
			</div>
		</div>
	);
};
